-- Міграція V002: Додавання перевірки для позицій замовлення
ALTER TABLE "order_item" ADD CONSTRAINT "chk_quantity_positive" CHECK ("quantity" > 0);