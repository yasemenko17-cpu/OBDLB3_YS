"""Робота з PostgreSQL у тестах: з'єднання, тимчасова схема, потоки, очікування блокувань.

Параметри з'єднання беруться зі змінних середовища PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
(у Codespaces вони вже задані). Типові значення: localhost, 5432, postgres, postgres, postgres.

Порядок подій у конкурентних тестах задається явно, без випадкових затримок: тест зупиняє ваш код у
відомій точці (параметр hook чи обробник), запускає конкурента в окремому потоці й чекає, доки той
або завершиться, або стане в очікування блокування (pg_stat_activity.wait_event_type = 'Lock').
"""
import os
import threading
import time
import uuid

import psycopg
import pytest

LOCK_TIMEOUT_MS = 8000


def settings():
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "user": os.environ.get("PGUSER", "postgres"),
        "password": os.environ.get("PGPASSWORD", "postgres"),
        "dbname": os.environ.get("PGDATABASE", "postgres"),
    }


def _connect(schema, app, autocommit):
    cfg = settings()
    try:
        conn = psycopg.connect(connect_timeout=5, application_name=app,
                               options=f"-c search_path={schema} -c lock_timeout={LOCK_TIMEOUT_MS}", **cfg)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"Немає з'єднання з PostgreSQL ({cfg['host']}:{cfg['port']}): {exc}\n"
            "Запустіть сервер: у Codespaces він стартує разом із середовищем; локально виконайте\n"
            "  docker run --name lab-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:18\n"
            "і за потреби задайте PGHOST, PGPORT, PGUSER, PGPASSWORD.",
            pytrace=False)
    conn.autocommit = True
    try:  # швидше виявлення взаємних блокувань; потребує прав суперкористувача, інакше лишається типове значення
        conn.execute("SET deadlock_timeout = '100ms'")
    except psycopg.Error:
        pass
    conn.autocommit = autocommit
    return conn


class Worker:
    """Потік із власним з'єднанням: виконує fn(conn) і зберігає результат або виняток."""

    def __init__(self, lab, fn, level=None):
        self.conn = lab.conn(level)
        self.pid = self.conn.info.backend_pid
        self.result = None
        self.error = None
        self.finished = threading.Event()
        self._lab = lab
        self._fn = fn
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            self.result = self._fn(self.conn)
        except BaseException as exc:  # noqa: BLE001
            self.error = exc
        finally:
            self.finished.set()

    def start(self):
        self._thread.start()
        return self

    def join(self, timeout=10.0):
        """Чекає завершення потоку; повертає самого працівника."""
        self.finished.wait(timeout)
        if not self.finished.is_set():
            pytest.fail("Потік не завершився вчасно: імовірно, транзакцію не завершено або блокування не знято", pytrace=False)
        return self

    def value(self, timeout=10.0):
        """Результат функції; якщо вона підняла виняток, піднімає його тут."""
        self.join(timeout)
        if self.error is not None:
            raise self.error
        return self.result


class Meeting:
    """Зустріч потоків у відомій точці коду без залежності від швидкості машини.

    Учасник, що викликає arrive(), чекає, доки кожен із решти або теж дійшов до цієї точки, або
    стоїть в очікуванні блокування на сервері (тоді чекати на нього безглуздо)."""

    def __init__(self, lab, parties, timeout=6.0):
        self._probe = lab.conn(autocommit=True)
        self._guard = threading.Lock()
        self._reached = set()
        self._pids = {}
        self._parties = set(parties)
        self._timeout = timeout

    def register(self, party, pid):
        self._pids[party] = pid

    def _blocked(self, party):
        pid = self._pids.get(party)
        if pid is None:
            return False
        with self._guard:
            row = self._probe.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE pid = %s AND wait_event_type = 'Lock'", (pid,)).fetchone()
        return row[0] > 0

    def arrive(self, party):
        self._reached.add(party)
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            if all(p in self._reached or self._blocked(p) for p in self._parties - {party}):
                return
            time.sleep(0.01)


class Lab:
    """Середовище одного тесту: порожня тимчасова схема lab04_<токен> і засоби для сеансів та потоків."""

    def __init__(self):
        self.token = uuid.uuid4().hex[:10]
        self.schema = "lab04_" + self.token
        self.app = "lab04_" + self.token
        self._conns = []
        self._admin = None

    def __enter__(self):
        cfg = settings()
        try:
            bootstrap = psycopg.connect(connect_timeout=5, **cfg)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"Немає з'єднання з PostgreSQL ({cfg['host']}:{cfg['port']}): {exc}\n"
                        "Запустіть сервер (див. README) і задайте PGHOST, PGPORT, PGUSER, PGPASSWORD.", pytrace=False)
        bootstrap.autocommit = True
        bootstrap.execute(f'CREATE SCHEMA "{self.schema}"')
        bootstrap.close()
        self._admin = self.conn(autocommit=True)
        return self

    def __exit__(self, *exc):
        cfg = settings()
        try:
            cleaner = psycopg.connect(connect_timeout=5, **cfg)
            cleaner.autocommit = True
            cleaner.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                            "WHERE application_name = %s AND pid <> pg_backend_pid()", (self.app,))
            time.sleep(0.05)
            cleaner.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
            cleaner.close()
        except Exception:  # noqa: BLE001
            pass
        for conn in self._conns:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    # --- з'єднання і запити

    def conn(self, level=None, autocommit=False):
        """Нове з'єднання в тимчасовій схемі. За замовчуванням без автофіксації (як у вашому коді)."""
        conn = _connect(self.schema, self.app, autocommit)
        if level is not None:
            conn.isolation_level = level
        self._conns.append(conn)
        return conn

    def sql(self, text, params=None):
        """Виконує команди (підготовка даних) на окремому з'єднанні з автофіксацією."""
        self._admin.execute(text, params)

    def rows(self, text, params=None):
        """Результат запиту як список списків (з'єднання автофіксації бачить лише зафіксовані дані)."""
        return [list(r) for r in self._admin.execute(text, params).fetchall()]

    def value(self, text, params=None):
        return self._admin.execute(text, params).fetchone()[0]

    # --- потоки

    def worker(self, fn, level=None):
        """Запускає fn(conn) у новому потоці зі своїм з'єднанням."""
        return Worker(self, fn, level).start()

    def settle(self, worker, timeout=6.0):
        """Чекає, доки потік завершиться або стане в очікування блокування. Повертає "done" чи "blocked"."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if worker.finished.is_set():
                return "done"
            if self.value("SELECT count(*) FROM pg_stat_activity WHERE pid = %s AND wait_event_type = 'Lock'",
                          (worker.pid,)):
                return "blocked"
            time.sleep(0.01)
        return "timeout"

    def meeting(self, parties):
        return Meeting(self, parties)

    def advisory_locks(self):
        """Кількість наданих дорадчих блокувань усіх сеансів тимчасової схеми."""
        return self.value("SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                          "WHERE l.locktype = 'advisory' AND l.granted AND a.application_name = %s", (self.app,))

    def barrier(self, parties):
        return threading.Barrier(parties, timeout=10)
