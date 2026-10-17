"""Відкриті тести задачі 7: Черга завдань зі SKIP LOCKED.

Запуск: pytest tests/test_lab_07.py            (усі відкриті випадки)
        pytest tests/test_lab_07.py -k S2     (лише ваш набір, наприклад другий)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from labtools import Cases, fn, idle

T07 = Cases()
BATCH = "process_batch"


class Crash(BaseException):
    """Імітація аварійного завершення виконавця (не Exception, тому обробник помилок завдання її не перехоплює)."""


def setup(lab, priorities):
    lab.sql("CREATE TABLE jobs (id integer PRIMARY KEY, priority integer NOT NULL DEFAULT 0, payload text, "
            "status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')), "
            "worker text, attempts integer NOT NULL DEFAULT 0);")
    for number, priority in enumerate(priorities, 1):
        lab.sql("INSERT INTO jobs (id, priority, payload) VALUES (%s, %s, %s)", (number, priority, f"p{number}"))


def table(lab):
    return lab.rows("SELECT id, status, worker, attempts FROM jobs ORDER BY id")


def by_status(lab, status):
    return [r[0] for r in lab.rows("SELECT id FROM jobs WHERE status = %s ORDER BY id", (status,))]


def noop(job_id, payload):
    return None


def with_rival(lab, name, limit, seen, handler=noop):
    """Обробник виконавця A: перед першим завданням запускає конкурента B і чекає, що той не стане в очікування."""
    state = {"first": True}

    def inner(job_id, payload):
        if state["first"]:
            state["first"] = False
            rival = lab.worker(lambda c: fn(7, BATCH)(c, name, limit, handler))
            assert lab.settle(rival) == "done", \
                "виконавець чекає на рядки, які тримає інший: використайте FOR UPDATE SKIP LOCKED"
            seen.append(rival)
    return inner


@T07.case("S1", public=True)
def one_worker_follows_priority(lab):
    setup(lab, [0, 5, 5, 0])
    conn, order = lab.conn(), []
    done = fn(7, BATCH)(conn, "W1", 3, lambda i, p: order.append((i, p)))
    assert done == [2, 3, 1] and order == [(2, "p2"), (3, "p3"), (1, "p1")]
    assert table(lab) == [[1, "done", "W1", 1], [2, "done", "W1", 1], [3, "done", "W1", 1], [4, "pending", None, 0]]
    assert idle(conn)


@T07.case("S1", public=True)
def two_workers_take_different_jobs(lab):
    setup(lab, [0] * 6)
    conn, seen = lab.conn(), []
    done = fn(7, BATCH)(conn, "A", 2, with_rival(lab, "B", 2, seen))
    assert done == [1, 2]
    assert seen[0].value() == [3, 4]
    assert table(lab) == [[1, "done", "A", 1], [2, "done", "A", 1], [3, "done", "B", 1], [4, "done", "B", 1],
                          [5, "pending", None, 0], [6, "pending", None, 0]]


@T07.case("S2", public=True)
def failing_handler_marks_job_failed(lab):
    setup(lab, [0, 0, 0])
    lab.sql("UPDATE jobs SET payload = 'bad' WHERE id = 2")
    conn = lab.conn()

    def handler(job_id, payload):
        if payload == "bad":
            raise RuntimeError("не вдалося обробити")
    assert fn(7, BATCH)(conn, "W", 3, handler) == [1, 3]
    assert table(lab) == [[1, "done", "W", 1], [2, "failed", "W", 1], [3, "done", "W", 1]]
    assert fn(7, BATCH)(conn, "W", 3, handler) == [], "виконані й невдалі завдання повторно не беруть"


@T07.case("S2", public=True)
def crash_returns_jobs_to_the_queue(lab):
    setup(lab, [0, 0, 0, 0])
    conn, calls = lab.conn(), []

    def handler(job_id, payload):
        calls.append(job_id)
        if len(calls) == 2:
            raise Crash("аварія")
    with pytest.raises(Crash):
        fn(7, BATCH)(conn, "W", 3, handler)
    assert table(lab) == [[i, "pending", None, 0] for i in range(1, 5)], "аварійна пачка не повинна лишати слідів"
    assert idle(conn)
    assert fn(7, BATCH)(lab.conn(), "V", 4, noop) == [1, 2, 3, 4]


@T07.case("S3", public=True)
def three_workers_partition_the_queue(lab):
    setup(lab, [0] * 7)
    conn, seen_b, seen_c = lab.conn(), [], []
    handler_b = with_rival(lab, "C", 2, seen_c)
    done_a = fn(7, BATCH)(conn, "A", 2, with_rival(lab, "B", 2, seen_b, handler=handler_b))
    assert done_a == [1, 2]
    assert seen_b[0].value() == [3, 4]
    assert seen_c[0].value() == [5, 6]
    assert by_status(lab, "pending") == [7]


@pytest.mark.parametrize("sset,case_fn", T07.params(), ids=T07.ids("T07"))
def test_task_07(lab, sset, case_fn):
    case_fn(lab)
