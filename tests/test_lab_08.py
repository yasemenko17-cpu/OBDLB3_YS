"""Відкриті тести задачі 8: Дорадчі блокування.

Запуск: pytest tests/test_lab_08.py            (усі відкриті випадки)
        pytest tests/test_lab_08.py -k S2     (лише ваш набір, наприклад другий)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from labtools import Cases, expect_error, fn, idle

T08 = Cases()
RUN = "run_exclusive"
SETUP = "CREATE TABLE runlog (id serial PRIMARY KEY, note text NOT NULL);"


def outcome(worker):
    worker.join(timeout=15)
    if worker.error is not None:
        raise worker.error
    return worker.result


@T08.case("S1", public=True)
def free_lock_runs_the_action(lab):
    lab.sql(SETUP)
    conn, inside = lab.conn(), []

    def action(c):
        inside.append(lab.advisory_locks())
        return "звіт"
    assert fn(8, RUN)(conn, "nightly", action) == (True, "звіт")
    assert inside == [1], "під час дії сеанс має тримати одне дорадче блокування"
    assert lab.advisory_locks() == 0 and idle(conn)


@T08.case("S1", public=True)
def busy_lock_skips_the_action(lab):
    lab.sql(SETUP)
    conn, seen, skipped = lab.conn(), [], []

    def action_a(c):
        rival = lab.worker(lambda cc: fn(8, RUN)(cc, "nightly", lambda x: skipped.append("B працює")))
        assert lab.settle(rival) == "done", "неблокуючий запуск не повинен чекати"
        seen.append(rival)
        return "A"
    assert fn(8, RUN)(conn, "nightly", action_a) == (True, "A")
    assert outcome(seen[0]) == (False, None) and skipped == []
    assert fn(8, RUN)(lab.conn(), "nightly", lambda c: "знову") == (True, "знову")


@T08.case("S2", public=True)
def waiting_run_starts_after_the_first_finishes(lab):
    lab.sql(SETUP)
    conn, events, seen = lab.conn(), [], []

    def action_a(c):
        events.append("A:start")
        rival = lab.worker(lambda cc: fn(8, RUN)(cc, "job", lambda x: events.append("B:run") or "B", wait=True))
        assert lab.settle(rival) == "blocked", "запуск із wait=True має чекати, доки блокування вільне"
        seen.append(rival)
        events.append("A:end")
        return "A"
    assert fn(8, RUN)(conn, "job", action_a, wait=True) == (True, "A")
    assert outcome(seen[0]) == (True, "B")
    assert events == ["A:start", "A:end", "B:run"]


@T08.case("S3", public=True)
def error_in_action_releases_the_lock(lab):
    lab.sql(SETUP)
    conn = lab.conn()

    def action(c):
        c.execute("INSERT INTO runlog (note) VALUES ('перед помилкою')")
        raise RuntimeError("збій дії")
    with pytest.raises(RuntimeError):
        fn(8, RUN)(conn, "job", action)
    assert idle(conn) and lab.advisory_locks() == 0
    assert lab.rows("SELECT count(*) FROM runlog") == [[0]], "зміни дії з помилкою мають бути скасовані"
    assert fn(8, RUN)(conn, "job", lambda c: "ok") == (True, "ok")


@T08.case("S3", public=True)
def empty_name_is_rejected(lab):
    lab.sql(SETUP)
    conn, calls = lab.conn(), []
    expect_error(lambda: fn(8, RUN)(conn, "", lambda c: calls.append(1)), "Порожнє ім'я блокування")
    expect_error(lambda: fn(8, RUN)(conn, "", lambda c: calls.append(1), wait=True), "Порожнє ім'я блокування")
    assert calls == [] and idle(conn)


@pytest.mark.parametrize("sset,case_fn", T08.params(), ids=T08.ids("T08"))
def test_task_08(lab, sset, case_fn):
    case_fn(lab)
