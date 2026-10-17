"""Задача 9. Паралельні клієнти: скрипт навантаження на SERIALIZABLE із повтором і перевірка інваріантів.

Прочитайте опис задачі 9 в інструкції (розділ 7) і картку свого варіанта (розділ 8).
Використовуйте лише стандартну бібліотеку Python і драйвер psycopg (він уже є в requirements.txt).
"""
import random  # noqa: F401
import threading  # noqa: F401

import psycopg  # noqa: F401


def run_workload(connect, clients: int, ops: int, accounts: int, max_amount: int, seed: int,
                 max_attempts: int = 50) -> dict:
    """Запускає clients потоків по ops переказів кожен і повертає звіт committed/rejected/failed/retries (задача 9)."""
    raise NotImplementedError("Реалізуйте функцію run_workload за описом задачі 9")


def check_invariants(conn, initial: dict, hook=None) -> list:
    """Перевіряє баланси за єдиним знімком даних і повертає список повідомлень про порушення (задача 9)."""
    raise NotImplementedError("Реалізуйте функцію check_invariants за описом задачі 9")
