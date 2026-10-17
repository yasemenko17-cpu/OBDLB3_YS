"""Перевірник наскрізного проєкту (частина Б, конкурентна операція): розгортання проєкту, паралельний прогін, Git.

Запуск:  python project_check/check_project.py [тека_проєкту]   або   pytest project_check
Тека проєкту за замовчуванням: project/ (поруч із цим файлом на рівень вище). Змінна PROJECT_DIR задає іншу теку.
Потрібен PostgreSQL (змінні PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE). Перевірник працює в тимчасовій
схемі, яку видаляє. Кожне зауваження має код (MIG03, LOAD05, POST02, CONC03, GIT06 тощо) і пояснення.
Перевірник відповідає на питання «чи розгортається проєкт і чи тримається інваріант операції за паралельного
навантаження»; змістову якість вибору операції та захисту переглядає викладач.
"""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent
MIN_MIGRATIONS = 3
MIN_TABLES = 6
MIN_ROWS_PER_TABLE = 3
MIN_ROWS_TOTAL = 150
MIN_ROWS_BIG = 50
MIN_COMMITS = 5
MIN_MIGRATION_COMMITS = 3
MIN_CONCURRENCY_COMMITS = 2
WORKERS = 6
CALLS_PER_WORKER = 8
NOTE_SECTIONS = ("Інваріант", "Захист", "Що було б без захисту")
NOTE_MIN_WORDS = 12
TECHNIQUES = {
    "for_update": r"FOR\s+UPDATE|FOR\s+NO\s+KEY\s+UPDATE",
    "optimistic": r"\bversion\b|updated_at|\bxmin\b",
    "serializable": r"SERIALIZABLE",
    "skip_locked": r"SKIP\s+LOCKED",
    "advisory": r"advisory",
    "constraint": r"UniqueViolation|ExclusionViolation|ON\s+CONFLICT|23505|23P01",
}
RETRY_MARK = re.compile(r"40001|40P01|SerializationFailure|DeadlockDetected|TransactionRollback")
PLACEHOLDERS = {"", "—", "-", "...", "ЗАПОВНІТЬ", "TBD"}
MIGRATION_NAME = re.compile(r"V(\d+)__([a-z0-9_]+)\.sql")
COPY_LINE = re.compile(r"""^\\copy\s+(?P<table>"[^"]+"|\w+)\s*(?P<cols>\([^)]*\))?\s+from\s+'(?P<file>[^']+)'\s*(?P<rest>.*?);?\s*$""",
                       re.I)
INVARIANT_HEAD = re.compile(r"^--\s*invariant:\s*(.+?)\s*$", re.I)


def _connect():
    cfg = dict(host=os.environ.get("PGHOST", "localhost"), port=int(os.environ.get("PGPORT", "5432")),
               user=os.environ.get("PGUSER", "postgres"), password=os.environ.get("PGPASSWORD", "postgres"),
               dbname=os.environ.get("PGDATABASE", "postgres"))
    conn = psycopg.connect(connect_timeout=5, **cfg)
    conn.autocommit = True
    return conn, cfg


def checksum(text):
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return hashlib.sha256("\n".join(lines).rstrip("\n").encode("utf-8")).hexdigest()[:12]


def _first_line(exc):
    return str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__


# ---------------------------------------------------------------- каталог

_COLUMNS = """
SELECT c.relname::text, a.attname::text, format_type(a.atttypid, a.atttypmod), a.attnotnull, a.attidentity::text
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace JOIN pg_attribute a ON a.attrelid = c.oid
WHERE n.nspname = current_schema() AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""
_CONSTRAINTS = """
SELECT rel.relname::text, con.contype::text,
  (SELECT array_agg(att.attname::text ORDER BY k.ord) FROM unnest(con.conkey) WITH ORDINALITY AS k(num, ord)
     JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = k.num),
  frel.relname::text,
  (SELECT array_agg(att.attname::text ORDER BY k.ord) FROM unnest(con.confkey) WITH ORDINALITY AS k(num, ord)
     JOIN pg_attribute att ON att.attrelid = con.confrelid AND att.attnum = k.num),
  con.convalidated
FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace n ON n.oid = rel.relnamespace LEFT JOIN pg_class frel ON frel.oid = con.confrelid
WHERE n.nspname = current_schema() AND con.contype IN ('p', 'u', 'f', 'c')
"""


def read_catalog(cur):
    """{таблиця: {"columns": [(ім'я, тип, обов'язковий, identity)], "pk": [...], "unique": [...], "fks": [...], "checks": n}}."""
    tables = {}
    cur.execute(_COLUMNS)
    for table, col, typ, notnull, ident in cur.fetchall():
        t = tables.setdefault(table, {"columns": [], "pk": [], "unique": [], "fks": [], "checks": 0})
        t["columns"].append((col, typ, notnull, ident != ""))
    cur.execute(_CONSTRAINTS)
    for table, kind, cols, ftable, fcols, valid in cur.fetchall():
        t = tables[table]
        if kind == "p":
            t["pk"] = list(cols)
        elif kind == "u":
            t["unique"].append(list(cols))
        elif kind == "f":
            t["fks"].append({"columns": list(cols), "ref_table": ftable, "ref_columns": list(fcols), "valid": valid})
        else:
            t["checks"] += 1
    return tables


def _q(name):
    return '"' + name.replace('"', '""') + '"'


@contextmanager
def scratch(prefix="proj"):
    """Тимчасова схема з search_path; повертає (курсор, назва схеми); після виходу схема видаляється."""
    conn, _ = _connect()
    name = f"{prefix}_{uuid.uuid4().hex[:10]}"
    cur = conn.cursor()
    try:
        cur.execute(f'CREATE SCHEMA "{name}"')
        cur.execute(f'SET search_path = "{name}"')
        yield cur, name
    finally:
        try:
            cur.execute("ROLLBACK")
        except Exception:  # noqa: BLE001
            pass
        try:
            cur.execute("SET search_path = public")
            cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        finally:
            conn.close()


# ---------------------------------------------------------------- міграції


def list_migrations(project):
    """[(версія, ім'я файлу, текст)] за зростанням версії і зауваження за іменами."""
    folder = project / "migrations"
    if not folder.is_dir():
        return [], ["MIG00: немає теки migrations/ (файли V001__назва.sql, V002__назва.sql, ...)"]
    out, problems, seen = [], [], {}
    for path in sorted(folder.glob("*.sql")):
        m = MIGRATION_NAME.fullmatch(path.name)
        if not m:
            problems.append(f"MIG01: ім'я файлу {path.name} не відповідає шаблону V<число>__<назва>.sql (малі літери, цифри, підкреслення)")
            continue
        version = int(m.group(1))
        if version in seen:
            problems.append(f"MIG01: версія {version} повторюється у файлах {seen[version]} і {path.name}")
            continue
        seen[version] = path.name
        out.append((version, path.name, path.read_text(encoding="utf-8")))
    out.sort()
    if len(out) < MIN_MIGRATIONS:
        problems.append(f"MIG02: міграцій {len(out)}, потрібно щонайменше {MIN_MIGRATIONS} (початкова схема і ще дві зміни)")
    return out, problems


def apply_all(cur, migrations):
    """Застосовує міграції по одній у транзакції й записує їх у schema_migrations. Повертає (кількість, зауваження)."""
    cur.execute("CREATE TABLE schema_migrations (version integer PRIMARY KEY, name text NOT NULL, checksum text NOT NULL, "
                "applied_at timestamptz NOT NULL DEFAULT now())")
    done = 0
    for version, name, sql in migrations:
        cur.execute("BEGIN")
        try:
            cur.execute(sql)
            cur.execute("INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)", (version, name, checksum(sql)))
            cur.execute("COMMIT")
        except psycopg.Error as exc:
            cur.execute("ROLLBACK")
            return done, [f"MIG03: міграція {name} відхилена сервером: {_first_line(exc)}"]
        done += 1
    return done, []


def check_migrations(project, cur):
    migrations, problems = list_migrations(project)
    if not migrations:
        return None, problems
    done, errs = apply_all(cur, migrations)
    problems += errs
    if errs:
        return None, problems
    catalog = {t: v for t, v in read_catalog(cur).items() if t != "schema_migrations"}
    first = migrations[0][2]
    if len(re.findall(r"create\s+table", first, re.I)) < MIN_TABLES:
        problems.append(f"MIG04: у першій міграції {migrations[0][1]} менше {MIN_TABLES} команд CREATE TABLE "
                        "(вона має містити схему з LAB01)")
    later = " ".join(m[2] for m in migrations[1:])
    if not re.search(r"\balter\s+table\b|\bcreate\s+(unique\s+)?index\b", later, re.I):
        problems.append("MIG05: пізніші міграції не містять жодної команди ALTER TABLE або CREATE INDEX (міграція має змінювати структуру)")
    if len(catalog) < MIN_TABLES:
        problems.append(f"MIG06: після міграцій у схемі {len(catalog)} таблиць, потрібно щонайменше {MIN_TABLES}")
    for name, t in sorted(catalog.items()):
        if not t["pk"]:
            problems.append(f"MIG07: таблиця {name} не має первинного ключа")
    cur.execute("SELECT count(*) FROM schema_migrations")
    if cur.fetchone()[0] != len(migrations):
        problems.append("MIG08: журнал schema_migrations не збігається з кількістю міграцій")
    return catalog, problems


# ---------------------------------------------------------------- завантаження даних


def parse_load(project):
    """[(номер рядка, таблиця, список стовпців або None, файл, решта параметрів)] і зауваження."""
    path = project / "load.psql"
    if not path.exists():
        return [], ["LOAD00: немає файлу load.psql (команди \\copy у порядку завантаження)"]
    out, problems = [], []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("--") or line.startswith("\\set") or line.startswith("\\echo"):
            continue
        m = COPY_LINE.match(line)
        if not m:
            problems.append(f"LOAD01: load.psql, рядок {number}: очікується \\copy таблиця [(стовпці)] FROM 'файл' WITH (FORMAT csv, HEADER true)")
            continue
        table = m.group("table").strip('"')
        out.append((number, table, m.group("cols"), m.group("file"), m.group("rest") or "WITH (FORMAT csv, HEADER true)"))
    return out, problems


def run_load(project, cur, catalog):
    commands, problems = parse_load(project)
    loaded = {}
    for number, table, cols, file, rest in commands:
        if table not in catalog:
            problems.append(f"LOAD02: load.psql, рядок {number}: таблиці {table} немає у схемі")
            continue
        path = (project / file)
        if not path.is_file():
            problems.append(f"LOAD03: load.psql, рядок {number}: немає файлу {file}")
            continue
        if table in loaded:
            problems.append(f"LOAD04: таблицю {table} завантажено двічі (рядок {number})")
            continue
        sql = f"COPY {_q(table)} {cols or ''} FROM STDIN {rest}"
        try:
            with cur.copy(sql) as cp:
                cp.write(path.read_bytes())
        except psycopg.Error as exc:
            problems.append(f"LOAD05: load.psql, рядок {number}, таблиця {table}: {_first_line(exc)} "
                            "(перевірте порядок: спершу батьківські таблиці, потім дочірні; і формат CSV)")
            continue
        cur.execute(f"SELECT count(*) FROM {_q(table)}")
        loaded[table] = cur.fetchone()[0]
    for table in sorted(set(catalog) - {name for _, name, *_ in commands}):
        problems.append(f"LOAD06: таблиця {table} не завантажується: у load.psql немає команди \\copy для неї")
    for table, n in sorted(loaded.items()):
        if n < MIN_ROWS_PER_TABLE:
            problems.append(f"LOAD07: у таблиці {table} {n} рядків, потрібно щонайменше {MIN_ROWS_PER_TABLE}")
    if loaded:
        total = sum(loaded.values())
        if total < MIN_ROWS_TOTAL:
            problems.append(f"LOAD08: усього рядків {total}, потрібно щонайменше {MIN_ROWS_TOTAL}")
        if max(loaded.values()) < MIN_ROWS_BIG:
            problems.append(f"LOAD09: немає жодної таблиці з {MIN_ROWS_BIG}+ рядками (згенеруйте дані скриптом make_data.py)")
    if not (project / "make_data.py").exists():
        problems.append("LOAD10: немає скрипта make_data.py, що генерує CSV (дані мають відтворюватися)")
    return loaded, problems


def _sql_body(text):
    return re.sub(r"--[^\n]*", "", text).strip()


def check_post_load(project, cur, catalog):
    path = project / "post_load.sql"
    if not path.exists():
        return ["POST00: немає файлу post_load.sql (вирівнювання послідовностей після завантаження)"]
    text = path.read_text(encoding="utf-8")
    out = []
    if _sql_body(text):
        try:
            cur.execute(text)
        except psycopg.Error as exc:
            return [f"POST01: post_load.sql відхилено сервером: {_first_line(exc)}"]
    for table, t in sorted(catalog.items()):
        for col, _, _, identity in t["columns"]:
            if not identity:
                continue
            cur.execute(f"SELECT max({_q(col)}) FROM {_q(table)}")
            top = cur.fetchone()[0]
            cur.execute("SELECT nextval(pg_get_serial_sequence(%s, %s))", (_q(table), col))
            nxt = cur.fetchone()[0]
            if top is not None and nxt <= top:
                out.append(f"POST02: у {table}.{col} наступне значення послідовності {nxt} не більше за максимум {top} "
                           "(додайте в post_load.sql setval(...))")
    return out



# ---------------------------------------------------------------- конкурентна операція


def _strip_comments(source):
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))


def _read_invariant(folder):
    """(опис, запит, зауваження) з concurrency/invariant.sql."""
    path = folder / "invariant.sql"
    lines = path.read_text(encoding="utf-8").splitlines()
    title, body = None, []
    for raw in lines:
        m = INVARIANT_HEAD.match(raw.strip())
        if m and title is None:
            title = m.group(1)
        elif not raw.strip().startswith("--"):
            body.append(raw)
    sql = "\n".join(body).strip().rstrip(";").strip()
    problems = []
    if title is None or title in PLACEHOLDERS or title.startswith("ЗАПОВНІТЬ"):
        problems.append("CONC06: у invariant.sql немає рядка «-- invariant: опис правила» (або опис не заповнено)")
    if not re.match(r"(?is)^(with|select)\b", sql):
        problems.append("CONC06: invariant.sql має містити запит SELECT (або WITH ... SELECT), що повертає порушення")
    elif re.fullmatch(r"(?is)select\s+1\s+where\s+false", sql):
        problems.append("CONC06: invariant.sql містить лише запит-заглушку: запишіть реальну перевірку інваріанта")
    return title, sql, problems


def _check_notes(folder):
    text = (folder / "NOTES.md").read_text(encoding="utf-8")
    out = []
    for name in NOTE_SECTIONS:
        m = re.search(rf"^##\s+{re.escape(name)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
        if not m:
            out.append(f"CONC16: у NOTES.md немає розділу «## {name}»")
            continue
        body = m.group(1)
        words = re.findall(r"[\w'’-]+", body)
        if "ЗАПОВНІТЬ" in body or len(words) < NOTE_MIN_WORDS:
            out.append(f"CONC16: розділ «{name}» у NOTES.md порожній або містить заглушку (потрібно щонайменше {NOTE_MIN_WORDS} слів)")
    return out


def _run_workers(module, cfg, schema):
    """Паралельний прогін perform: повертає (кількість успішних, кількість відмов, зауваження)."""
    problems, lock = {}, threading.Lock()
    counts = {"ok": 0, "rejected": 0}
    barrier = threading.Barrier(WORKERS, timeout=30)

    def note(code, text):
        with lock:
            problems.setdefault(code, f"{code}: {text}")

    def run(worker):
        conn = psycopg.connect(connect_timeout=5, application_name="lab04_project",
                               options=f"-c search_path={schema} -c lock_timeout=10000", **cfg)
        try:
            barrier.wait()
            for i in range(CALLS_PER_WORKER):
                try:
                    module.perform(conn, worker, i)
                    with lock:
                        counts["ok"] += 1
                except ValueError:
                    with lock:
                        counts["rejected"] += 1
                except psycopg.Error as exc:
                    if exc.sqlstate in ("40001", "40P01"):
                        note("CONC11", f"операція не обробила помилку {exc.sqlstate} ({_first_line(exc)}): "
                                       "повторіть транзакцію або змініть прийом захисту")
                    else:
                        note("CONC12", f"операція завершилась помилкою сервера: {_first_line(exc)}")
                except Exception as exc:  # noqa: BLE001
                    note("CONC12", f"операція завершилась винятком {type(exc).__name__}: {exc}")
                if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                    note("CONC13", "після виклику perform транзакцію лишено відкритою: завершуйте її COMMIT або ROLLBACK")
                if conn.closed:
                    break
                try:
                    conn.rollback()
                except psycopg.Error:
                    pass
        except threading.BrokenBarrierError:
            pass
        finally:
            conn.close()

    threads = [threading.Thread(target=run, args=(k,)) for k in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=90)
    return counts["ok"], counts["rejected"], list(problems.values()), list(problems)


def check_concurrency(project, cur, schema, cfg, catalog):
    folder = project / "concurrency"
    out = []
    if not folder.is_dir():
        return ["CONC00: немає теки concurrency/ (operation.py, invariant.sql, concurrency.json, NOTES.md)"]
    for name in ("operation.py", "invariant.sql", "concurrency.json", "NOTES.md"):
        if not (folder / name).is_file():
            out.append(f"CONC00: немає файлу concurrency/{name}")
    if out:
        return out
    try:
        meta = json.loads((folder / "concurrency.json").read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"CONC01: concurrency.json не є коректним JSON: {exc}"]
    technique = meta.get("technique")
    if technique not in TECHNIQUES:
        out.append(f"CONC01: technique має бути одним із {', '.join(TECHNIQUES)}")
    tables = meta.get("tables")
    if not isinstance(tables, list) or not tables or any(str(t).startswith("ЗАПОВНІТЬ") for t in tables):
        out.append("CONC01: concurrency.json: у tables перелічіть таблиці, до яких звертається операція")
    else:
        for t in tables:
            if t not in catalog:
                out.append(f"CONC05: таблиці {t} із concurrency.json немає у схемі проєкту")
    if str(meta.get("operation", "")).startswith("ЗАПОВНІТЬ") or not str(meta.get("operation", "")).strip():
        out.append("CONC01: concurrency.json: опишіть операцію в полі operation")
    source = _strip_comments((folder / "operation.py").read_text(encoding="utf-8"))
    if technique in TECHNIQUES and not re.search(TECHNIQUES[technique], source, re.I):
        out.append(f"CONC03: у operation.py не видно прийому «{technique}» (очікується збіг із {TECHNIQUES[technique]})")
    if technique in ("optimistic", "serializable") and not RETRY_MARK.search(source):
        out.append("CONC04: прийом допускає конфлікти 40001, але operation.py не містить повтору транзакції (40001/40P01)")
    title, sql, problems = _read_invariant(folder)
    out += problems
    if not problems:
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            if rows:
                out.append(f"CONC08: інваріант порушено ще до навантаження: {len(rows)} рядків, перший: {tuple(rows[0])!r}")
        except psycopg.Error as exc:
            out.append(f"CONC07: invariant.sql не виконується: {_first_line(exc)}")
            problems.append("x")
    try:
        spec = importlib.util.spec_from_file_location("project_operation", folder / "operation.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not callable(getattr(module, "perform", None)):
            raise AttributeError("у модулі немає функції perform(conn, worker, i)")
    except Exception as exc:  # noqa: BLE001
        out.append(f"CONC09: operation.py не завантажується: {type(exc).__name__}: {exc}")
        return out + _check_notes(folder)
    prep = getattr(module, "prepare", None)
    if callable(prep):
        conn = psycopg.connect(connect_timeout=5, options=f"-c search_path={schema}", **cfg)
        try:
            prep(conn)
            conn.commit()
        except NotImplementedError:
            out.append("CONC09: perform/prepare у operation.py ще не реалізовано")
            return out + _check_notes(folder)
        except Exception as exc:  # noqa: BLE001
            out.append(f"CONC10: prepare завершилась помилкою: {type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}")
        finally:
            conn.close()
    ok, rejected, notes, codes = _run_workers(module, cfg, schema)
    out += notes
    if "CONC12" in codes and any("NotImplementedError" in n for n in notes):
        out.append("CONC09: perform у operation.py ще не реалізовано")
    elif ok == 0 and not notes:
        out.append("CONC14: жодна операція не виконалась (усі відмови ValueError): перевірте prepare і дані")
    if not problems:
        try:
            cur.execute("ROLLBACK")
        except psycopg.Error:
            pass
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            if rows:
                out.append(f"CONC15: після паралельного прогону інваріант порушено: {len(rows)} рядків, перший: {tuple(rows[0])!r}")
        except psycopg.Error as exc:
            out.append(f"CONC07: invariant.sql після прогону не виконується: {_first_line(exc)}")
    return out + _check_notes(folder)


# ---------------------------------------------------------------- Git


def _git(project, *args):
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True)


def check_git(project):
    try:
        top = _git(project, "rev-parse", "--show-toplevel")
    except FileNotFoundError:
        return ["GIT00: команда git не знайдена"]
    if top.returncode != 0:
        return ["GIT01: теку проєкту не під керуванням Git (виконайте git init, git add, git commit)"]
    out = []
    count = _git(project, "rev-list", "--count", "HEAD")
    n = int(count.stdout.strip() or 0) if count.returncode == 0 else 0
    if n < MIN_COMMITS:
        out.append(f"GIT02: комітів {n}, потрібно щонайменше {MIN_COMMITS} (історія LAB02 і окремі коміти конкурентної операції)")
    tracked = set(_git(project, "ls-files", "--", ".").stdout.split())
    for f in ("load.psql", "post_load.sql", "make_data.py"):
        if f not in tracked:
            out.append(f"GIT03: файл {f} не додано в Git")
    for sub in ("migrations", "data", "concurrency"):
        if not any(t.startswith(sub + "/") for t in tracked):
            out.append(f"GIT03: у Git немає жодного файлу з теки {sub}/")
    log = _git(project, "log", "--format=%H", "--", "migrations")
    if len([x for x in log.stdout.split() if x]) < MIN_MIGRATION_COMMITS:
        out.append(f"GIT05: теку migrations/ змінено менш ніж у {MIN_MIGRATION_COMMITS} комітах "
                   "(кожну міграцію фіксуйте окремим комітом)")
    log = _git(project, "log", "--format=%H", "--", "concurrency")
    commits = len([x for x in log.stdout.split() if x])
    if commits < MIN_CONCURRENCY_COMMITS:
        out.append(f"GIT06: теку concurrency/ змінено у {commits} комітах, потрібно щонайменше {MIN_CONCURRENCY_COMMITS} "
                   "(спершу операція без захисту та інваріант, потім захист)")
    if _git(project, "status", "--porcelain", "--", ".").stdout.strip():
        out.append("GIT04: є незафіксовані зміни у теці проєкту (git status)")
    return out


# ---------------------------------------------------------------- все разом


def deploy_and_check(project):
    """Розгортає проєкт у тимчасовій схемі й запускає конкурентну операцію. Повертає (каталог, зауваження)."""
    out = []
    try:
        with scratch() as (cur, schema):
            catalog, problems = check_migrations(project, cur)
            out += problems
            if catalog is None:
                return None, out
            loaded, problems = run_load(project, cur, catalog)
            out += problems
            out += check_post_load(project, cur, catalog)
            out += check_concurrency(project, cur, schema, _settings(), catalog)
            return catalog, out
    except psycopg.OperationalError as exc:
        return None, [f"MIG00: немає з'єднання з PostgreSQL ({_first_line(exc)}); запустіть сервер і задайте PGHOST, PGPORT тощо"]


def _settings():
    return dict(host=os.environ.get("PGHOST", "localhost"), port=int(os.environ.get("PGPORT", "5432")),
                user=os.environ.get("PGUSER", "postgres"), password=os.environ.get("PGPASSWORD", "postgres"),
                dbname=os.environ.get("PGDATABASE", "postgres"))


def check_all(project, git=True):
    project = Path(project)
    catalog, out = deploy_and_check(project)
    if git:
        out += check_git(project)
    return out


def main(argv):
    project = Path(argv[1]) if len(argv) > 1 else Path(os.environ.get("PROJECT_DIR", ROOT.parent / "project"))
    problems = check_all(project)
    for p in problems:
        print(p)
    print(f"Зауважень: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
