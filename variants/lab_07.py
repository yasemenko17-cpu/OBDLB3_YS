"""Задача 7. Черга завдань: кілька виконавців беруть різні рядки завдяки SKIP LOCKED.

Прочитайте опис задачі 7 в інструкції (розділ 7) і картку свого варіанта (розділ 8).
Використовуйте лише стандартну бібліотеку Python і драйвер psycopg (він уже є в requirements.txt).
"""
import psycopg  # noqa: F401


def process_batch(conn, worker: str, limit: int, handler) -> list:
    """Бере до limit завдань у стані pending, обробляє їх handler(id, payload) і повертає номери виконаних (задача 7)."""
    raise NotImplementedError("Реалізуйте функцію process_batch за описом задачі 7")
