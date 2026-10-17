SELECT setval(pg_get_serial_sequence('"customer"', 'id'), coalesce(max("id"), 0) + 1, false) FROM "customer";
SELECT setval(pg_get_serial_sequence('"category"', 'id'), coalesce(max("id"), 0) + 1, false) FROM "category";
SELECT setval(pg_get_serial_sequence('"supplier"', 'id'), coalesce(max("id"), 0) + 1, false) FROM "supplier";
SELECT setval(pg_get_serial_sequence('"product"', 'id'), coalesce(max("id"), 0) + 1, false) FROM "product";
SELECT setval(pg_get_serial_sequence('"orders"', 'id'), coalesce(max("id"), 0) + 1, false) FROM "orders";
SELECT setval(pg_get_serial_sequence('"warehouse"', 'id'), coalesce(max("id"), 0) + 1, false) FROM "warehouse";