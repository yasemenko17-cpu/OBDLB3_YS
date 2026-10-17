"""Генерує CSV-файли теки data/ детермінованим способом: повторний запуск дає ті самі файли.

Запуск (з теки project):  python make_data.py
Генератор випадкових чисел створюйте з фіксованим зерном: random.Random(42).
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"
rnd = random.Random(42)


def write(name, header, rows):
    with (OUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)

    # 1. Category (5 рядків)
    categories = [
        (1, "Електроніка"),
        (2, "Одяг"),
        (3, "Дім і сад"),
        (4, "Спорт"),
        (5, "Книги"),
    ]
    write("category", ["id", "title"], categories)

    # 2. Supplier (5 рядків)
    suppliers = [
        (1, "ТОВ 'ТехноПром'"),
        (2, "ПП 'Стиль'"),
        (3, "АгроСвіт"),
        (4, "СпортТрейд"),
        (5, "Видавництво 'Основа'"),
    ]
    write("supplier", ["id", "name"], suppliers)

    # 3. Warehouse (3 рядки)
    warehouses = [
        (1, "Київський центральний склад"),
        (2, "Львівський логістичний центр"),
        (3, "Одеський термінал"),
    ]
    write("warehouse", ["id", "location"], warehouses)

    # 4. Customer (30 рядків)
    cities = ["Київ", "Львів", "Одеса", "Харків", "Дніпро"]
    streets = ["Шевченка", "Студентська", "Центральна", "Паркова", "Київська"]
    customers = []
    for i in range(1, 31):
        email = f"user{i:03d}@example.com"
        phone = f"+38067{rnd.randint(1000000, 9999999)}"
        city = rnd.choice(cities)
        street = f"{rnd.choice(streets)}, {rnd.randint(1, 100)}"
        customers.append((i, email, phone, city, street))
    write("customer", ["id", "email", "phone", "address_city", "address_street"], customers)

    # 5. Customer Alt Phones (20 рядків)
    alt_phones = []
    for i in range(1, 21):
        c_id = rnd.randint(1, 30)
        phone = f"+38050{rnd.randint(1000000, 9999999)}"
        alt_phones.append((c_id, phone))
    # Видаляємо можливі дублікати первинного ключа (customer_id, value)
    alt_phones = list(set(alt_phones))
    write("customer_alt_phones", ["customer_id", "value"], alt_phones)

    # 6. Product (40 рядків)
    products = []
    for i in range(1, 41):
        name = f"Товар №{i}"
        price = round(rnd.uniform(50.0, 5000.0), 2)
        cat_id = rnd.randint(1, 5)
        sup_id = rnd.randint(1, 5)
        products.append((i, name, price, cat_id, sup_id))
    write("product", ["id", "name", "price", "category_id", "supplier_id"], products)

    # 7. Orders (60 рядків — виконує умову 50+ рядків в одній таблиці)
    statuses = ["Новий", "В обробці", "Відправлено", "Доставлено"]
    start_date = date(2025, 1, 1)
    orders = []
    for i in range(1, 61):
        o_date = start_date + timedelta(days=rnd.randint(0, 300))
        status = rnd.choice(statuses)
        cust_id = rnd.randint(1, 30)
        orders.append((i, o_date.isoformat(), status, cust_id))
    write("orders", ["id", "order_date", "status", "customer_id"], orders)

    # 8. Order Item (120 рядків)
    order_items = []
    for o_id in range(1, 61):
        # Кожне замовлення має 1-3 позиції
        items_count = rnd.randint(1, 3)
        for item_no in range(1, items_count + 1):
            qty = rnd.randint(1, 5)
            prod_id = rnd.randint(1, 40)
            order_items.append((o_id, item_no, qty, prod_id))
    write("order_item", ["orders_id", "item_no", "quantity", "product_id"], order_items)

    # 9. Stock (40 рядків)
    stocks = []
    for w_id in range(1, 4):
        for s_id in range(1, 15):
            qty = rnd.randint(0, 100)
            p_id = rnd.randint(1, 40)
            stocks.append((w_id, s_id, qty, p_id))
    # Унікальність за (warehouse_id, stock_id)
    stocks_unique = []
    seen = set()
    for s in stocks:
        key = (s[0], s[1])
        if key not in seen:
            seen.add(key)
            stocks_unique.append(s)
    write("stock", ["warehouse_id", "stock_id", "quantity", "product_id"], stocks_unique)

    print("Успішно згенеровано всі CSV-файли у теці data/!")


if __name__ == "__main__":
    main()