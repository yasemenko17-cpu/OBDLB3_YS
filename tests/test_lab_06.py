"""Відкриті тести задачі 6: Бронювання ресурсу без перебронювання.

Запуск: pytest tests/test_lab_06.py            (усі відкриті випадки)
        pytest tests/test_lab_06.py -k S2     (лише ваш набір, наприклад другий)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from datetime import datetime
from labtools import Cases, expect_error, fn, idle

T06 = Cases()
RESERVE = "reserve"
BUSY = "Ресурс 1 зайнятий на цей час"


def t(hour, minute=0):
    return datetime(2030, 5, 1, hour, minute)


def setup(lab, capacity=1):
    lab.sql("CREATE TABLE resources (id integer PRIMARY KEY, title text NOT NULL, capacity integer NOT NULL CHECK (capacity > 0));"
            "CREATE TABLE reservations (id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, "
            "resource_id integer NOT NULL REFERENCES resources, who text NOT NULL, "
            "start_at timestamp NOT NULL, end_at timestamp NOT NULL CHECK (end_at > start_at));")
    lab.sql("INSERT INTO resources VALUES (1, 'Кімната', %s), (2, 'Запасна кімната', 1)", (capacity,))


def book(lab, conn, resource, who, h1, h2, **kwargs):
    return fn(6, RESERVE)(conn, resource, who, t(h1), t(h2), **kwargs)


def rows(lab):
    return lab.rows("SELECT resource_id, who, to_char(start_at, 'HH24:MI'), to_char(end_at, 'HH24:MI') "
                    "FROM reservations ORDER BY id")


def outcome(worker):
    worker.join(timeout=15)
    if isinstance(worker.error, ValueError):
        return str(worker.error)
    if worker.error is not None:
        raise worker.error
    return worker.result


def rival_hook(lab, rivals, plans):
    """Хук: на першій спробі запускає конкурентів і чекає, доки кожен завершиться або стане в очікування."""
    def hook(attempt):
        if attempt != 1:
            return
        for resource, who, h1, h2 in plans:
            worker = lab.worker(lambda c, r=resource, w=who, a=h1, b=h2: book(lab, c, r, w, a, b))
            rivals.append(worker)
            assert lab.settle(worker) in ("done", "blocked")
    return hook


def only_one_wins(results):
    wins = [r for r in results if isinstance(r, int)]
    refused = [r for r in results if isinstance(r, str)]
    assert len(wins) == 1 and refused == [BUSY], f"очікувалось одне бронювання й одна відмова, отримано {results!r}"


@T06.case("S1", public=True)
def basic_reservation(lab):
    setup(lab)
    conn = lab.conn()
    assert book(lab, conn, 1, "Оля", 10, 11) == 1
    assert rows(lab) == [[1, "Оля", "10:00", "11:00"]]
    assert idle(conn)


@T06.case("S1", public=True)
def interval_boundaries(lab):
    setup(lab)
    conn = lab.conn()
    assert book(lab, conn, 1, "Оля", 10, 11) == 1
    assert book(lab, conn, 1, "Іван", 11, 12) == 2, "кінець одного бронювання не перетинається з початком наступного"
    assert book(lab, conn, 1, "Марія", 9, 10) == 3
    for who, h1, m1, h2, m2 in [("А", 10, 30, 11, 30), ("Б", 9, 30, 10, 30), ("В", 10, 15, 10, 45), ("Г", 8, 0, 13, 0)]:
        expect_error(lambda: fn(6, RESERVE)(conn, 1, who, t(h1, m1), t(h2, m2)), BUSY)
    assert len(rows(lab)) == 3 and idle(conn)


@T06.case("S1", public=True)
def race_for_the_same_slot(lab):
    setup(lab)
    conn, rivals = lab.conn(), []
    hook = rival_hook(lab, rivals, [(1, "Іван", 10, 11)])
    try:
        mine = book(lab, conn, 1, "Оля", 10, 11, hook=hook)
    except ValueError as exc:
        mine = str(exc)
    only_one_wins([mine, outcome(rivals[0])])
    assert len(rows(lab)) == 1


@T06.case("S2", public=True)
def capacity_of_three(lab):
    setup(lab, 3)
    conn = lab.conn()
    for who in ("А", "Б", "В"):
        assert isinstance(book(lab, conn, 1, who, 10, 12), int)
    expect_error(lambda: book(lab, conn, 1, "Г", 11, 13), BUSY)
    assert isinstance(book(lab, conn, 1, "Г", 12, 13), int)
    assert len(rows(lab)) == 4


@T06.case("S2", public=True)
def race_for_the_last_place(lab):
    setup(lab, 3)
    conn, rivals = lab.conn(), []
    book(lab, conn, 1, "А", 10, 12)
    book(lab, conn, 1, "Б", 10, 12)
    hook = rival_hook(lab, rivals, [(1, "Ґ", 10, 12)])
    try:
        mine = book(lab, conn, 1, "В", 11, 13, hook=hook)
    except ValueError as exc:
        mine = str(exc)
    only_one_wins([mine, outcome(rivals[0])])
    assert len(rows(lab)) == 3


@T06.case("S3", public=True)
def own_overlapping_reservation(lab):
    setup(lab, 3)
    conn = lab.conn()
    assert isinstance(book(lab, conn, 1, "Оля", 10, 12), int)
    expect_error(lambda: book(lab, conn, 1, "Оля", 11, 13), "Оля уже має бронювання на цей час")
    assert isinstance(book(lab, conn, 1, "Оля", 12, 13), int)
    assert isinstance(book(lab, conn, 1, "Іван", 10, 12), int)
    assert len(rows(lab)) == 3


@pytest.mark.parametrize("sset,case_fn", T06.params(), ids=T06.ids("T06"))
def test_task_06(lab, sset, case_fn):
    case_fn(lab)
