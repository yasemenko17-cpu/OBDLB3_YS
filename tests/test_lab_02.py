"""Відкриті тести задачі 2: Ідемпотентний платіж.

Запуск: pytest tests/test_lab_02.py            (усі відкриті випадки)
        pytest tests/test_lab_02.py -k S2     (лише ваш набір, наприклад другий)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from labtools import Cases, expect_error, fn, idle

T02 = Cases()
PAY = "pay"
SETUP = (
    "CREATE TABLE accounts (id integer PRIMARY KEY, balance integer NOT NULL CHECK (balance >= 0));"
    "CREATE TABLE payments (key text PRIMARY KEY, account_id integer NOT NULL, amount integer NOT NULL, "
    "balance_after integer NOT NULL);"
    "INSERT INTO accounts VALUES (1, 100), (2, 40);"
)


def balances(lab):
    return lab.rows("SELECT id, balance FROM accounts ORDER BY id")


@T02.case("S1", public=True)
def first_request_is_applied(lab):
    lab.sql(SETUP)
    conn = lab.conn()
    assert fn(2, PAY)(conn, "order-1", 1, 30) == ("applied", 70)
    assert balances(lab) == [[1, 70], [2, 40]]
    assert lab.rows("SELECT key, account_id, amount, balance_after FROM payments") == [["order-1", 1, 30, 70]]
    assert idle(conn)


@T02.case("S1", public=True)
def repeated_request_changes_nothing(lab):
    lab.sql(SETUP)
    conn = lab.conn()
    pay = fn(2, PAY)
    assert pay(conn, "order-1", 1, 30) == ("applied", 70)
    assert pay(conn, "order-1", 1, 30) == ("duplicate", 70)
    assert pay(conn, "order-1", 1, 30) == ("duplicate", 70)
    assert balances(lab) == [[1, 70], [2, 40]]
    assert lab.value("SELECT count(*) FROM payments") == 1
    assert idle(conn)


@T02.case("S2", public=True)
def key_reused_with_other_parameters(lab):
    lab.sql(SETUP)
    conn = lab.conn()
    pay = fn(2, PAY)
    assert pay(conn, "k", 1, 30) == ("applied", 70)
    expect_error(lambda: pay(conn, "k", 1, 31), "Ключ k уже використано з іншими параметрами")
    expect_error(lambda: pay(conn, "k", 2, 30), "Ключ k уже використано з іншими параметрами")
    assert balances(lab) == [[1, 70], [2, 40]]
    assert idle(conn)


@T02.case("S2", public=True)
def failed_payment_does_not_store_key(lab):
    lab.sql(SETUP)
    conn = lab.conn()
    pay = fn(2, PAY)
    expect_error(lambda: pay(conn, "big", 2, 41), "Недостатньо коштів на рахунку 2")
    assert lab.value("SELECT count(*) FROM payments") == 0, "ключ невдалого платежу не зберігають"
    assert idle(conn)
    lab.sql("UPDATE accounts SET balance = 100 WHERE id = 2")
    assert pay(conn, "big", 2, 41) == ("applied", 59), "після поповнення той самий ключ має спрацювати"


@T02.case("S3", public=True)
def concurrent_duplicates_apply_once(lab):
    lab.sql(SETUP)
    start = lab.barrier(5)

    def run(conn):
        start.wait()
        return fn(2, PAY)(conn, "same", 1, 30)
    workers = [lab.worker(run) for _ in range(5)]
    results = [w.value() for w in workers]
    assert sorted(r[0] for r in results) == ["applied"] + ["duplicate"] * 4
    assert {r[1] for r in results} == {70}
    assert balances(lab) == [[1, 70], [2, 40]]
    assert lab.value("SELECT count(*) FROM payments") == 1


@T02.case("S3", public=True)
def concurrent_distinct_keys_all_apply(lab):
    lab.sql(SETUP)
    start = lab.barrier(4)

    def make(i):
        def run(conn):
            start.wait()
            return fn(2, PAY)(conn, f"k{i}", 1, 10)
        return run
    workers = [lab.worker(make(i)) for i in range(4)]
    results = [w.value() for w in workers]
    assert sorted(r[1] for r in results) == [60, 70, 80, 90]
    assert balances(lab)[0] == [1, 60]
    assert lab.value("SELECT count(*) FROM payments") == 4


@pytest.mark.parametrize("sset,case_fn", T02.params(), ids=T02.ids("T02"))
def test_task_02(lab, sset, case_fn):
    case_fn(lab)
