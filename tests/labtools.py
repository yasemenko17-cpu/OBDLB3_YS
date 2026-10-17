"""Спільні засоби відкритих і повних тестів: реєстр випадків, завантаження функцій, перевірні помічники."""
import psycopg
import pytest
from conftest import load


class Cases:
    """Реєстр випадків однієї задачі: кожен випадок належить набору умов S1, S2 або S3."""

    def __init__(self):
        self.items = []

    def case(self, sset, public=False):
        def register(fn):
            self.items.append((sset, fn))
            return fn
        return register

    def params(self):
        return [(s, fn) for s, fn in self.items]

    def ids(self, prefix):
        return [f"{prefix}-{s}-{i}" for i, (s, _) in enumerate(self.items)]


def fn(task, name):
    """Функція вашої задачі за номером задачі й назвою."""
    return getattr(load(task), name)


def idle(conn):
    """Істина, якщо з'єднання не перебуває всередині транзакції."""
    return conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE


def expect_error(callable_, message):
    """Викликає callable_ і перевіряє, що виник ValueError із точним текстом."""
    with pytest.raises(ValueError) as info:
        callable_()
    assert str(info.value) == message, f"текст помилки: отримано {str(info.value)!r}, очікувалось {message!r}"
