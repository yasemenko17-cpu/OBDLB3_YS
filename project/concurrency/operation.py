import hashlib


def prepare(conn):
  """Підготовка перед навантажувальним тестом (опціонально)."""
  pass


def perform(conn, worker, i):
  """Виконує списання товару під консультативним блокуванням."""
  # Виправляємо отримання зрізу байтів через .digest()
  hash_bytes = hashlib.sha256(b"stock_update_exclusive").digest()
  lock_key = int.from_bytes(hash_bytes[:8], byteorder="big", signed=True)
  
  cursor = conn.cursor()

  try:
    # Отримуємо консультативне блокування транзакційного рівня без очікування
    cursor.execute("SELECT pg_try_advisory_xact_lock(%s);", (lock_key,))
    acquired = cursor.fetchone()[0]

    if not acquired:
      conn.rollback()
      raise ValueError("Ресурс заблоковано іншим воркером")

    # Безпечне оновлення складського залишку
    cursor.execute(
        "UPDATE stock SET quantity = quantity - 1 WHERE product_id = 1 AND"
        " quantity > 0;"
    )

    conn.commit()
  except BaseException:
    conn.rollback()
    raise