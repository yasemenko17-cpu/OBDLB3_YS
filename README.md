# Стартовий проєкт OBDZ-LAB04

1. Відкрийте проєкт у GitHub Codespaces (Code → Codespaces → Create codespace): разом із середовищем стартує сервер PostgreSQL 18, а в терміналі доступна команда `psql`. Локально: `python3 -m venv .venv`, `source .venv/bin/activate`, `pip install -r requirements.txt` і окремо запустіть PostgreSQL 18, наприклад `docker run --name lab-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:18`.
2. Визначте свою задачу й набір за номером варіанта: задача = `(номер - 1) // 3 + 1`, набір = `(номер - 1) % 3 + 1`. Реалізуйте функції у файлі `variants/lab_NN.py` за карткою варіанта.
3. Запускайте відкриті тести своєї задачі й свого набору: `pytest tests/test_lab_NN.py -k S2` (замініть `S2` на `S1`, `S2` або `S3`). Усі тести цієї роботи звертаються до PostgreSQL: перевірте змінні PGHOST, PGPORT, PGUSER, PGPASSWORD (у Codespaces вони вже задані; типові значення localhost, 5432, postgres, postgres).
4. Тести відтворюють конкуренцію керовано: другий сеанс або потік запускається в точці, яку тест обирає сам (параметр `hook`, обробник завдання, дія під блокуванням), без випадкових затримок. Тому результат не залежить від швидкості комп'ютера.
5. Змінюйте лише свій файл у `variants/` і теку `project/` (за бажанням додавайте `tests/test_my.py`).
6. Частина Б: перенесіть проєкт із OBDZ-LAB02 у теку `project/`, додайте теку `concurrency/` (операція, інваріант, пояснення) і перевірте командою `pytest project_check`. Розгорнути проєкт у схемі `project` вашої бази для ручних дослідів у двох сеансах `psql`: `python project_check/deploy_project.py`.
