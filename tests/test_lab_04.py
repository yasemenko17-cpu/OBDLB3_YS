"""Відкриті тести задачі 4: Зняття коштів з блокуванням рядка.

Запуск: pytest tests/test_lab_04.py            (усі відкриті випадки)
        pytest tests/test_lab_04.py -k S2     (лише ваш набір, наприклад другий)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from labtools import Cases, expect_error, fn, idle

T04 = Cases()
WITHDRAW = "withdraw"
SETUP = (
    "CREATE TABLE accounts (id integer PRIMARY KEY, balance integer NOT NULL CHECK (balance >= 0));"
    "INSERT INTO accounts VALUES (1, 100), (2, 80);"
)


def balances(lab):
    return lab.rows("SELECT id, balance FROM accounts ORDER BY id")


def outcome(worker):
    """Результат потоку як значення або текст помилки ValueError."""
    worker.join()
    if isinstance(worker.error, ValueError):
        return str(worker.error)
    if worker.error is not None:
        raise worker.error
    return worker.result


@T04.case("S1", public=True)
def simple_withdraw(lab):
    lab.sql(SETUP)
    conn = lab.conn()
    assert fn(4, WITHDRAW)(conn, 1, 30) == 70
    assert balances(lab) == [[1, 70], [2, 80]]
    assert idle(conn)


@T04.case("S1", public=True)
def second_withdraw_waits_for_the_first(lab):
    lab.sql(SETUP)
    conn, seen = lab.conn(), []

    def hook():
        if seen:
            return
        seen.append(1)
        rival = lab.worker(lambda c: fn(4, WITHDRAW)(c, 1, 50))
        assert lab.settle(rival) == "blocked", "рядок рахунку має бути заблоковано до завершення транзакції"
        seen.append(rival)
    assert fn(4, WITHDRAW)(conn, 1, 70, hook=hook) == 30
    assert outcome(seen[1]) == "Недостатньо коштів на рахунку 1", "конкурент має побачити вже зменшений залишок"
    assert balances(lab) == [[1, 30], [2, 80]]


@T04.case("S2", public=True)
def nowait_on_free_account(lab):
    lab.sql(SETUP)
    conn = lab.conn()
    assert fn(4, WITHDRAW)(conn, 2, 30, wait=False) == 50
    assert balances(lab) == [[1, 100], [2, 50]]


@T04.case("S2", public=True)
def nowait_on_busy_account(lab):
    lab.sql(SETUP)
    holder, conn = lab.conn(), lab.conn()
    holder.execute("SELECT 1 FROM accounts WHERE id = 1 FOR UPDATE")
    expect_error(lambda: fn(4, WITHDRAW)(conn, 1, 10, wait=False), "Рахунок 1 зайнятий іншою транзакцією")
    assert idle(conn)
    assert fn(4, WITHDRAW)(conn, 2, 10, wait=False) == 70, "інший рахунок не заблоковано"
    holder.rollback()
    assert fn(4, WITHDRAW)(conn, 1, 10, wait=False) == 90


@T04.case("S3", public=True)
def invalid_requests_change_nothing(lab):
    lab.sql(SETUP)
    conn = lab.conn()
    run = fn(4, WITHDRAW)
    expect_error(lambda: run(conn, 1, 0), "Сума має бути додатною")
    expect_error(lambda: run(conn, 1, -5), "Сума має бути додатною")
    expect_error(lambda: run(conn, 9, 10), "Рахунок не знайдено: 9")
    expect_error(lambda: run(conn, 1, 101), "Недостатньо коштів на рахунку 1")
    assert balances(lab) == [[1, 100], [2, 80]] and idle(conn)
    assert run(conn, 1, 100) == 0


@T04.case("S3", public=True)
def five_parallel_withdrawals_never_overdraw(lab):
    lab.sql(SETUP)
    start = lab.barrier(5)

    def run(conn):
        start.wait()
        return fn(4, WITHDRAW)(conn, 1, 30)
    workers = [lab.worker(run) for _ in range(5)]
    results = [outcome(w) for w in workers]
    assert sorted(r for r in results if isinstance(r, int)) == [10, 40, 70]
    assert results.count("Недостатньо коштів на рахунку 1") == 2
    assert balances(lab) == [[1, 10], [2, 80]]


@pytest.mark.parametrize("sset,case_fn", T04.params(), ids=T04.ids("T04"))
def test_task_04(lab, sset, case_fn):
    case_fn(lab)
