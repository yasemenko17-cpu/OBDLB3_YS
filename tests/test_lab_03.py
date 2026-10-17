"""Відкриті тести задачі 3: Переказ з оптимістичним блокуванням.

Запуск: pytest tests/test_lab_03.py            (усі відкриті випадки)
        pytest tests/test_lab_03.py -k S2     (лише ваш набір, наприклад другий)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from labtools import Cases, expect_error, fn, idle

T03 = Cases()
TRANSFER = "transfer_optimistic"
SETUP = (
    "CREATE TABLE accounts (id integer PRIMARY KEY, balance integer NOT NULL CHECK (balance >= 0), "
    "version integer NOT NULL DEFAULT 0);"
    "INSERT INTO accounts (id, balance) VALUES (1, 100), (2, 50);"
)
WIDE = (
    "CREATE TABLE accounts (id integer PRIMARY KEY, balance integer NOT NULL CHECK (balance >= 0), "
    "version integer NOT NULL DEFAULT 0);"
    "INSERT INTO accounts (id, balance) VALUES (1, 1000), (2, 0), (3, 0), (4, 0);"
)


def state(lab):
    return lab.rows("SELECT id, balance, version FROM accounts ORDER BY id")


def competitor(lab, account, delta, only_first=True):
    """Підказка для тесту: хук, що від імені конкурента змінює рахунок (з підвищенням версії)."""
    calls = []

    def hook(attempt):
        calls.append(attempt)
        if not only_first or attempt == 1:
            lab.sql("UPDATE accounts SET balance = balance + %s, version = version + 1 WHERE id = %s", (delta, account))
    hook.calls = calls
    return hook


@T03.case("S1", public=True)
def no_conflict(lab):
    lab.sql(SETUP)
    conn = lab.conn()
    assert fn(3, TRANSFER)(conn, 1, 2, 30) == 1
    assert state(lab) == [[1, 70, 1], [2, 80, 1]]
    assert idle(conn)


@T03.case("S1", public=True)
def conflict_on_source_is_detected(lab):
    lab.sql(SETUP)
    conn = lab.conn()
    hook = competitor(lab, 1, -10)
    assert fn(3, TRANSFER)(conn, 1, 2, 30, hook=hook) == 2
    assert hook.calls == [1, 2]
    assert state(lab) == [[1, 60, 2], [2, 80, 1]], "оновлення конкурента не можна втрачати"


@T03.case("S2", public=True)
def attempts_are_exhausted(lab):
    lab.sql(SETUP)
    conn = lab.conn()
    hook = competitor(lab, 1, -10, only_first=False)
    expect_error(lambda: fn(3, TRANSFER)(conn, 1, 2, 30, hook=hook), "Конфлікт версій після 3 спроб")
    assert hook.calls == [1, 2, 3]
    assert state(lab) == [[1, 70, 3], [2, 50, 0]], "невдалі спроби не повинні лишити змін"
    assert idle(conn)


@T03.case("S3", public=True)
def parallel_transfers_between_two_accounts(lab):
    lab.sql(WIDE)
    start = lab.barrier(6)

    def run(conn):
        start.wait()
        return fn(3, TRANSFER)(conn, 1, 2, 10, max_attempts=100)
    results = [w.value() for w in [lab.worker(run) for _ in range(6)]]
    assert all(isinstance(r, int) and r >= 1 for r in results)
    assert state(lab) == [[1, 940, 6], [2, 60, 6], [3, 0, 0], [4, 0, 0]]


@pytest.mark.parametrize("sset,case_fn", T03.params(), ids=T03.ids("T03"))
def test_task_03(lab, sset, case_fn):
    case_fn(lab)
