"""Задача 4. Зняття коштів: блокування рядка рахунку командою SELECT ... FOR UPDATE (і NOWAIT).

Прочитайте опис задачі 4 в інструкції (розділ 7) і картку свого варіанта (розділ 8).
Використовуйте лише стандартну бібліотеку Python і драйвер psycopg (він уже є в requirements.txt).
"""
import psycopg  # noqa: F401


def withdraw(conn, account_id: int, amount: int, wait: bool = True, hook=None) -> int:
    """Знімає amount з рахунку, заблокувавши його рядок; повертає новий залишок (задача 4)."""
    raise NotImplementedError("Реалізуйте функцію withdraw за описом задачі 4")
