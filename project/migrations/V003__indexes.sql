-- Міграція V003: Створення індексів для зовнішніх ключів
CREATE INDEX "idx_orders_customer_id" ON "orders" ("customer_id");
CREATE INDEX "idx_product_category_id" ON "product" ("category_id");