-- invariant: Кількість товарів на складі не може бути від'ємною
SELECT product_id, quantity FROM stock WHERE quantity < 0;