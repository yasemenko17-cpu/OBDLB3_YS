"""Відкриті тести задачі 9: Паралельні клієнти й перевірка інваріанта.

Запуск: pytest tests/test_lab_09.py            (усі відкриті випадки)
        pytest tests/test_lab_09.py -k S2     (лише ваш набір, наприклад другий)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import random
import pytest
from labtools import Cases, fn, idle

T09 = Cases()
WORK, CHECK = "run_workload", "check_invariants"


def setup(lab, accounts, balance, guarded=True):
    check = " CHECK (balance >= 0)" if guarded else ""
    lab.sql(f"CREATE TABLE accounts (id integer PRIMARY KEY, balance integer NOT NULL{check});"
            "CREATE TABLE transfers (id serial PRIMARY KEY, src integer NOT NULL, dst integer NOT NULL, "
            "amount integer NOT NULL);")
    lab.sql("INSERT INTO accounts SELECT g, %s FROM generate_series(1, %s) g", (balance, accounts))
    return {i: balance for i in range(1, accounts + 1)}


def factory(lab, made):
    def connect():
        conn = lab.conn()
        made.append(conn)
        return conn
    return connect


def plan(seed, client, ops, accounts, max_amount):
    rng = random.Random(seed * 1000 + client)
    out = []
    for _ in range(ops):
        src = rng.randint(1, accounts)
        dst = rng.randint(1, accounts - 1)
        if dst >= src:
            dst += 1
        out.append([src, dst, rng.randint(1, max_amount)])
    return out


def inject(lab, failures=0, require_serializable=False):
    """Тригер на вставку в transfers: штучні помилки 40001 (перші failures вставок) і перевірка рівня ізоляції."""
    lab.sql("CREATE SEQUENCE fault_seq")
    lab.sql(f"""CREATE FUNCTION inject() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF {str(require_serializable).lower()} AND current_setting('transaction_isolation') <> 'serializable' THEN
        RAISE EXCEPTION 'клієнти мають працювати на рівні SERIALIZABLE' USING ERRCODE = 'P0001';
      END IF;
      IF nextval('fault_seq') <= {failures} THEN
        RAISE EXCEPTION 'could not serialize access (штучний збій)' USING ERRCODE = '40001';
      END IF;
      RETURN NEW;
    END $$""")
    lab.sql("CREATE TRIGGER inject BEFORE INSERT ON transfers FOR EACH ROW EXECUTE FUNCTION inject()")


def transfers(lab):
    return lab.rows("SELECT src, dst, amount FROM transfers ORDER BY id")


def audit(lab, initial, hook=None):
    conn = lab.conn()
    result = fn(9, CHECK)(conn, initial, hook=hook) if hook else fn(9, CHECK)(conn, initial)
    assert idle(conn), "після перевірки з'єднання не повинно лишатися в транзакції"
    return result


@T09.case("S1", public=True)
def consistent_state_has_no_problems(lab):
    initial = setup(lab, 3, 100)
    lab.sql("INSERT INTO transfers (src, dst, amount) VALUES (1, 2, 30), (2, 3, 10)")
    lab.sql("UPDATE accounts SET balance = 70 WHERE id = 1")
    lab.sql("UPDATE accounts SET balance = 120 WHERE id = 2")
    lab.sql("UPDATE accounts SET balance = 110 WHERE id = 3")
    assert audit(lab, initial) == []


@T09.case("S1", public=True)
def negative_balance_is_reported(lab):
    initial = setup(lab, 2, 50, guarded=False)
    lab.sql("INSERT INTO transfers (src, dst, amount) VALUES (1, 2, 80)")
    lab.sql("UPDATE accounts SET balance = -30 WHERE id = 1")
    lab.sql("UPDATE accounts SET balance = 130 WHERE id = 2")
    assert audit(lab, initial) == ["Від'ємний баланс рахунку 1: -30"]


@T09.case("S2", public=True)
def single_client_follows_the_seeded_plan(lab):
    initial = setup(lab, 5, 1000)
    made = []
    report = fn(9, WORK)(factory(lab, made), 1, 20, 5, 9, 7)
    assert report == {"committed": 20, "rejected": 0, "failed": 0, "retries": 0}
    assert transfers(lab) == plan(7, 0, 20, 5, 9)
    assert audit(lab, initial) == []
    assert all(c.closed for c in made), "усі з'єднання клієнтів треба закрити"


@T09.case("S2", public=True)
def four_clients_keep_the_invariants(lab):
    initial = setup(lab, 6, 1000)
    report = fn(9, WORK)(factory(lab, []), 4, 10, 6, 5, 3)
    assert set(report) == {"committed", "rejected", "failed", "retries"}
    assert report["committed"] == 40 and report["rejected"] == 0 and report["failed"] == 0
    assert report["retries"] >= 0
    assert lab.value("SELECT count(*) FROM transfers") == 40
    assert audit(lab, initial) == []


@T09.case("S3", public=True)
def hot_spot_on_two_accounts(lab):
    initial = setup(lab, 2, 1000)
    report = fn(9, WORK)(factory(lab, []), 6, 8, 2, 5, 1, max_attempts=300)
    assert report["failed"] == 0 and report["committed"] == 48 and report["rejected"] == 0
    assert audit(lab, initial) == []


@pytest.mark.parametrize("sset,case_fn", T09.params(), ids=T09.ids("T09"))
def test_task_09(lab, sset, case_fn):
    case_fn(lab)
