"""Задача 1. Повтор транзакції при помилках серіалізації й взаємного блокування.

Прочитайте опис задачі 1 в інструкції (розділ 7) і картку свого варіанта (розділ 8).
Використовуйте лише стандартну бібліотеку Python і драйвер psycopg (він уже є в requirements.txt).
"""
import time  # noqa: F401

import psycopg  # noqa: F401


def run_with_retry(conn, body, isolation="READ COMMITTED", max_attempts=4, base_delay=0.05, max_delay=0.4,
                   sleep=time.sleep):
    """Виконує body(conn) в одній транзакції, повторюючи її при SQLSTATE 40001 і 40P01 (задача 1)."""
    raise NotImplementedError("Реалізуйте функцію run_with_retry за описом задачі 1")
