"""Відкриті тести задачі 5: Переказ з упорядкуванням блокувань.

Запуск: pytest tests/test_lab_05.py            (усі відкриті випадки)
        pytest tests/test_lab_05.py -k S2     (лише ваш набір, наприклад другий)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import psycopg
import pytest
from labtools import Cases, expect_error, fn, idle

T05 = Cases()
TRANSFER = "transfer"


def setup(lab, count=3, balance=100):
    lab.sql("CREATE TABLE accounts (id integer PRIMARY KEY, balance integer NOT NULL CHECK (balance >= 0));")
    lab.sql("INSERT INTO accounts SELECT g, %s FROM generate_series(1, %s) g", (balance, count))


def balances(lab):
    return [r[1] for r in lab.rows("SELECT id, balance FROM accounts ORDER BY id")]


def run_together(lab, plans):
    """Запускає перекази паралельно; кожен після блокування першого рядка зустрічається з рештою."""
    meet = lab.meeting(range(len(plans)))
    workers = []
    for k, (src, dst, amount) in enumerate(plans):
        def run(conn, k=k, src=src, dst=dst, amount=amount):
            return fn(5, TRANSFER)(conn, src, dst, amount, hook=lambda: meet.arrive(k))
        worker = lab.worker(run)
        meet.register(k, worker.pid)
        workers.append(worker)
    results = []
    for worker in workers:
        worker.join(timeout=15)
        if isinstance(worker.error, psycopg.errors.DeadlockDetected):
            pytest.fail("Сервер перервав транзакцію через взаємне блокування (40P01): "
                        "блокуйте рядки в одному й тому самому порядку, наприклад за зростанням id", pytrace=False)
        if worker.error is not None and not isinstance(worker.error, ValueError):
            raise worker.error
        results.append(worker.error if worker.error is not None else worker.result)
    return results


@T05.case("S1", public=True)
def sequential_transfer(lab):
    setup(lab, 2)
    conn = lab.conn()
    assert fn(5, TRANSFER)(conn, 1, 2, 30) == (70, 130)
    assert fn(5, TRANSFER)(conn, 2, 1, 50) == (80, 120)
    assert balances(lab) == [120, 80]
    assert idle(conn)


@T05.case("S1", public=True)
def opposite_transfers_do_not_deadlock(lab):
    setup(lab, 2)
    results = run_together(lab, [(1, 2, 30), (2, 1, 20)])
    assert all(isinstance(r, tuple) for r in results), results
    assert balances(lab) == [90, 110]


@T05.case("S2", public=True)
def ring_of_three(lab):
    setup(lab, 3)
    results = run_together(lab, [(1, 2, 10), (2, 3, 20), (3, 1, 30)])
    assert all(isinstance(r, tuple) for r in results), results
    assert balances(lab) == [120, 90, 90]


@T05.case("S3", public=True)
def refusal_releases_locks_for_the_other_transfer(lab):
    setup(lab, 2)
    results = run_together(lab, [(1, 2, 500), (2, 1, 10)])
    assert isinstance(results[0], ValueError) and str(results[0]) == "Недостатньо коштів на рахунку 1"
    assert results[1] == (90, 110)
    assert balances(lab) == [110, 90]


@T05.case("S3", public=True)
def missing_accounts_are_reported_in_lock_order(lab):
    setup(lab, 2)
    conn = lab.conn()
    run = fn(5, TRANSFER)
    expect_error(lambda: run(conn, 9, 1, 10), "Рахунок не знайдено: 9")
    expect_error(lambda: run(conn, 1, 9, 10), "Рахунок не знайдено: 9")
    expect_error(lambda: run(conn, 9, 7, 10), "Рахунок не знайдено: 7")
    assert idle(conn) and balances(lab) == [100, 100]


@pytest.mark.parametrize("sset,case_fn", T05.params(), ids=T05.ids("T05"))
def test_task_05(lab, sset, case_fn):
    case_fn(lab)
