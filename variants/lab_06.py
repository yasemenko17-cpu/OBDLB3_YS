"""Задача 6. Бронювання ресурсу з обмеженою місткістю без перебронювання за одночасних запитів.

Прочитайте опис задачі 6 в інструкції (розділ 7) і картку свого варіанта (розділ 8).
Використовуйте лише стандартну бібліотеку Python і драйвер psycopg (він уже є в requirements.txt).
"""
import psycopg  # noqa: F401


def reserve(conn, resource_id: int, who: str, start_at, end_at, hook=None, max_attempts: int = 5) -> int:
    """Створює бронювання [start_at, end_at) і повертає його номер (задача 6)."""
    raise NotImplementedError("Реалізуйте функцію reserve за описом задачі 6")
