import hashlib
import psycopg


def name_to_key(name: str) -> int:
  """Перетворює довільне ім'я на 64-бітне знакове ціле для advisory lock."""
  hash_bytes = hashlib.sha256(name.encode("utf-8")).digest()
  # Беремо перші 8 байтів та інтерпретуємо як знакове 64-бітне ціле (big-endian)
  return int.from_bytes(hash_bytes[:8], byteorder="big", signed=True)


def run_exclusive(conn, name, action, wait=False) -> tuple:
  """Виконує дію лише в одному сеансі за раз під консультативним блокуванням."""
  if not name:
    raise ValueError("Порожнє ім'я блокування")

  lock_key = name_to_key(name)
  cursor = conn.cursor()

  try:
    if wait:
      cursor.execute("SELECT pg_advisory_xact_lock(%s);", (lock_key,))
      acquired = True
    else:
      cursor.execute("SELECT pg_try_advisory_xact_lock(%s);", (lock_key,))
      acquired = cursor.fetchone()[0]

    if not acquired:
      conn.rollback()
      return (False, None)

    # Виконуємо дію, якщо блокування успішно отримано
    result = action(conn)
    conn.commit()
    return (True, result)

  except BaseException:
    conn.rollback()
    raise