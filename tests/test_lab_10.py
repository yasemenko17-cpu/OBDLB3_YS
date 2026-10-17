"""Відкриті тести задачі 10: Узгоджений звіт на знімку даних.

Запуск: pytest tests/test_lab_10.py            (усі відкриті випадки)
        pytest tests/test_lab_10.py -k S2     (лише ваш набір, наприклад другий)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from labtools import Cases, fn, idle

T10 = Cases()
REPORT = "consistent_report"
START = {"accounts": 3, "balance_total": 600, "ledger_total": 600, "ledger_rows": 3}
DEPOSIT = ("INSERT INTO ledger (account_id, delta) VALUES (3, 40);"
           "UPDATE accounts SET balance = balance + 40 WHERE id = 3;")
TRANSFER = ("INSERT INTO ledger (account_id, delta) VALUES (1, -50), (2, 50);"
            "UPDATE accounts SET balance = balance - 50 WHERE id = 1;"
            "UPDATE accounts SET balance = balance + 50 WHERE id = 2;")
NEW_ACCOUNT = ("INSERT INTO accounts VALUES (4, 70); INSERT INTO ledger (account_id, delta) VALUES (4, 70);")


def setup(lab, filled=True):
    lab.sql("CREATE TABLE accounts (id integer PRIMARY KEY, balance integer NOT NULL);"
            "CREATE TABLE ledger (id serial PRIMARY KEY, account_id integer NOT NULL, delta integer NOT NULL);")
    if filled:
        lab.sql("INSERT INTO accounts VALUES (1, 100), (2, 200), (3, 300);"
                "INSERT INTO ledger (account_id, delta) VALUES (1, 100), (2, 200), (3, 300);")


def after(lab, plan):
    """Хук: на вказаних кроках конкурент фіксує свої зміни (plan = {крок: SQL})."""
    def hook(step, conn):
        if step in plan:
            lab.sql(plan[step])
    return hook


def shown(conn, name):
    return conn.execute(f"SHOW {name}").fetchone()[0]


@T10.case("S1", public=True)
def quiet_database(lab):
    setup(lab)
    conn = lab.conn()
    assert fn(10, REPORT)(conn) == START
    assert idle(conn)


@T10.case("S1", public=True)
def commit_between_queries_is_invisible(lab):
    setup(lab)
    conn = lab.conn()
    report = fn(10, REPORT)(conn, hook=after(lab, {1: DEPOSIT}))
    assert report == START, "обидва запити мають читати стан на момент початку звіту"
    assert fn(10, REPORT)(conn) == {"accounts": 3, "balance_total": 640, "ledger_total": 640, "ledger_rows": 4}


@T10.case("S2", public=True)
def transaction_mode(lab):
    setup(lab)
    conn, seen = lab.conn(), []

    def hook(step, c):
        seen.append((step, shown(c, "transaction_isolation"), shown(c, "transaction_read_only")))
    fn(10, REPORT)(conn, hook=hook)
    assert [s[0] for s in seen] == [1, 2]
    for _, isolation, read_only in seen:
        assert isolation in ("repeatable read", "serializable"), f"рівень ізоляції {isolation!r} не дає єдиного знімка"
        assert read_only == "on", "звіт нічого не змінює: транзакція має бути лише для читання"


@T10.case("S2", public=True)
def writers_are_not_blocked(lab):
    setup(lab)
    conn, seen = lab.conn(), []

    def hook(step, c):
        if step == 1:
            def writer(cc):
                cc.execute("UPDATE accounts SET balance = balance + 1 WHERE id = 1")
                cc.execute("INSERT INTO ledger (account_id, delta) VALUES (1, 1)")
                cc.commit()
            worker = lab.worker(writer)
            assert lab.settle(worker) == "done", "звіт не повинен блокувати записувачів"
            seen.append(worker)
    assert fn(10, REPORT)(conn, hook=hook) == START
    seen[0].value()
    assert fn(10, REPORT)(conn)["balance_total"] == 601


@T10.case("S3", public=True)
def settings_are_restored(lab):
    setup(lab)
    conn = lab.conn()
    fn(10, REPORT)(conn)
    assert idle(conn)
    assert shown(conn, "transaction_isolation") == "read committed"
    assert shown(conn, "transaction_read_only") == "off"
    conn.execute("UPDATE accounts SET balance = balance WHERE id = 1")
    conn.commit()


@pytest.mark.parametrize("sset,case_fn", T10.params(), ids=T10.ids("T10"))
def test_task_10(lab, sset, case_fn):
    case_fn(lab)
