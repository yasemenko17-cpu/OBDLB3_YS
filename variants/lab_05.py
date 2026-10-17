"""Задача 5. Переказ без взаємного блокування: рядки блокують у фіксованому порядку.

Прочитайте опис задачі 5 в інструкції (розділ 7) і картку свого варіанта (розділ 8).
Використовуйте лише стандартну бібліотеку Python і драйвер psycopg (він уже є в requirements.txt).
"""
import psycopg  # noqa: F401


def transfer(conn, src: int, dst: int, amount: int, hook=None) -> tuple:
    """Переказує amount з src на dst; повертає нові залишки (src, dst) (задача 5)."""
    raise NotImplementedError("Реалізуйте функцію transfer за описом задачі 5")
