"""Розгортає проєкт у постійній схемі project вашої бази: міграції, дані, вирівнювання послідовностей (для ручних дослідів у двох сеансах psql).

Використання:  python project_check/deploy_project.py [тека_проєкту]
Стара схема project видаляється і створюється наново. Після розгортання таблиці видно в клієнті PostgreSQL
(схема project), а перевірки цілісності можна запускати вручну.
"""
import sys
from pathlib import Path

import check_project as cp


def main(project):
    conn, cfg = cp._connect()
    cur = conn.cursor()
    cur.execute("DROP SCHEMA IF EXISTS project CASCADE")
    cur.execute("CREATE SCHEMA project")
    cur.execute("SET search_path = project")
    migrations, problems = cp.list_migrations(project)
    done, errs = cp.apply_all(cur, migrations)
    problems += errs
    print(f"Застосовано міграцій: {done} із {len(migrations)}")
    if not errs:
        catalog = {t: v for t, v in cp.read_catalog(cur).items() if t != "schema_migrations"}
        loaded, errs = cp.run_load(project, cur, catalog)
        problems += errs
        for table, n in sorted(loaded.items()):
            print(f"  {table}: {n} рядків")
        problems += cp.check_post_load(project, cur, catalog)
    for p in problems:
        print(p)
    print(f"Схема project у базі {cfg['dbname']}: зауважень {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "project"))
