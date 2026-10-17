"""Відкриті тести задачі 1: Повтор транзакції при помилках серіалізації.

Запуск: pytest tests/test_lab_01.py            (усі відкриті випадки)
        pytest tests/test_lab_01.py -k S2     (лише ваш набір, наприклад другий)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from psycopg import errors
from labtools import Cases, fn, idle

T01 = Cases()
RUN = "run_with_retry"
ACCOUNTS = "CREATE TABLE acct (id integer PRIMARY KEY, balance integer NOT NULL); INSERT INTO acct VALUES (1, 100), (2, 50);"


class FlakyCommit:
    """Обгортка з'єднання: перші n викликів commit() завершуються помилкою серіалізації."""

    def __init__(self, conn, failures):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_left", failures)

    def commit(self):
        if self._left > 0:
            object.__setattr__(self, "_left", self._left - 1)
            self._conn.rollback()
            raise errors.SerializationFailure("could not serialize access")
        self._conn.commit()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        setattr(self._conn, name, value)


def conflicting_body(lab, other, calls, conflicts):
    """Тіло транзакції: читає рахунок 1, а під час перших спроб конкурент змінює його (конфлікт на REPEATABLE READ)."""
    def body(conn):
        calls.append(1)
        balance = conn.execute("SELECT balance FROM acct WHERE id = 1").fetchone()[0]
        if len(calls) <= conflicts:
            other.execute("UPDATE acct SET balance = balance + 10 WHERE id = 1")
            other.commit()
        conn.execute("UPDATE acct SET balance = %s WHERE id = 1", (balance - 30,))
        return balance
    return body


@T01.case("S1", public=True)
def first_attempt_succeeds(lab):
    lab.sql(ACCOUNTS)
    conn, sleeps = lab.conn(), []

    def body(c):
        c.execute("UPDATE acct SET balance = balance - 30 WHERE id = 1")
        return "готово"
    assert fn(1, RUN)(conn, body, sleep=sleeps.append) == ("готово", 1)
    assert sleeps == []
    assert lab.rows("SELECT balance FROM acct WHERE id = 1") == [[70]]
    assert idle(conn)


@T01.case("S1", public=True)
def one_conflict_then_success(lab):
    lab.sql(ACCOUNTS)
    other, conn, sleeps, calls = lab.conn(), lab.conn(), [], []
    body = conflicting_body(lab, other, calls, 1)
    result, attempts = fn(1, RUN)(conn, body, isolation="REPEATABLE READ", sleep=sleeps.append)
    assert attempts == 2 and len(calls) == 2
    assert result == 110, "друга спроба має прочитати вже змінений рахунок"
    assert lab.rows("SELECT balance FROM acct WHERE id = 1") == [[80]]
    assert sleeps == [pytest.approx(0.05)]


@T01.case("S2", public=True)
def deadlock_is_retried(lab):
    lab.sql(ACCOUNTS)
    conn, sleeps, calls = lab.conn(), [], []

    def body(c):
        calls.append(1)
        c.execute("UPDATE acct SET balance = balance + 1 WHERE id = 2")
        if len(calls) == 1:
            raise errors.DeadlockDetected("deadlock detected")
        return "ok"
    assert fn(1, RUN)(conn, body, sleep=sleeps.append) == ("ok", 2)
    assert lab.rows("SELECT balance FROM acct WHERE id = 2") == [[51]], "зміни невдалої спроби мають бути скасовані"
    assert sleeps == [pytest.approx(0.05)]


@T01.case("S2", public=True)
def unique_violation_is_not_retried(lab):
    lab.sql(ACCOUNTS)
    conn, sleeps, calls = lab.conn(), [], []

    def body(c):
        calls.append(1)
        c.execute("UPDATE acct SET balance = 0 WHERE id = 2")
        c.execute("INSERT INTO acct VALUES (1, 5)")
    with pytest.raises(errors.UniqueViolation):
        fn(1, RUN)(conn, body, sleep=sleeps.append)
    assert len(calls) == 1 and sleeps == []
    assert lab.rows("SELECT balance FROM acct WHERE id = 2") == [[50]]
    assert idle(conn)


@T01.case("S3", public=True)
def attempts_are_exhausted(lab):
    lab.sql(ACCOUNTS)
    conn, sleeps, calls = lab.conn(), [], []

    def body(c):
        calls.append(1)
        c.execute("UPDATE acct SET balance = balance + 1 WHERE id = 1")
        raise errors.SerializationFailure("could not serialize access")
    with pytest.raises(errors.SerializationFailure):
        fn(1, RUN)(conn, body, max_attempts=3, sleep=sleeps.append)
    assert len(calls) == 3
    assert sleeps == [pytest.approx(0.05), pytest.approx(0.1)], "після останньої спроби затримки немає"
    assert lab.rows("SELECT balance FROM acct WHERE id = 1") == [[100]]
    assert idle(conn)


@T01.case("S3", public=True)
def delay_is_capped(lab):
    conn, sleeps, calls = lab.conn(), [], []

    def body(c):
        calls.append(1)
        if len(calls) < 6:
            raise errors.SerializationFailure("x")
        return "ok"
    assert fn(1, RUN)(conn, body, max_attempts=6, base_delay=0.05, max_delay=0.15, sleep=sleeps.append) == ("ok", 6)
    assert sleeps == pytest.approx([0.05, 0.1, 0.15, 0.15, 0.15])


@pytest.mark.parametrize("sset,case_fn", T01.params(), ids=T01.ids("T01"))
def test_task_01(lab, sset, case_fn):
    case_fn(lab)
