"""Задача 3. Переказ з оптимістичним блокуванням: стовпець version і повтор при конфлікті.

Прочитайте опис задачі 3 в інструкції (розділ 7) і картку свого варіанта (розділ 8).
Використовуйте лише стандартну бібліотеку Python і драйвер psycopg (він уже є в requirements.txt).
"""
import psycopg  # noqa: F401


def transfer_optimistic(conn, src: int, dst: int, amount: int, max_attempts: int = 3, hook=None) -> int:
    """Переказує amount з рахунку src на dst без блокувань читання; повертає кількість використаних спроб (задача 3)."""
    raise NotImplementedError("Реалізуйте функцію transfer_optimistic за описом задачі 3")
