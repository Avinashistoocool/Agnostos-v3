"""Explicit, transactional account/job/contact transfer into an empty PostgreSQL DB."""
from __future__ import annotations

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, insert, select, text

from .database import DATA, engine, metadata, migrate


def transfer(source: Path, connection, cipher: Fernet) -> dict[str, int]:
    if not source.is_file():
        raise ValueError("Source SQLite file does not exist")
    for table in metadata.sorted_tables:
        if connection.scalar(select(func.count()).select_from(table)):
            raise ValueError("Destination is not empty; transfer refused")
    counts = {}
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as old:
        old.row_factory = sqlite3.Row
        tables = {row[0] for row in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "users" not in tables:
            raise ValueError("Source is not an Agnostos database (no users table)")
        for table in metadata.sorted_tables:
            if table.name not in tables:
                continue
            cursor = old.execute(f'SELECT * FROM "{table.name}"')
            count = 0
            while batch := cursor.fetchmany(500):
                records = [dict(row) for row in batch]
                if table.name == "users":
                    for row in records:
                        if row["settings"]:
                            try:
                                cipher.decrypt(row["settings"])
                            except InvalidToken:
                                raise ValueError("APP_SECRET cannot decrypt source settings; use the original key") from None
                connection.execute(insert(table), records)
                count += len(records)
            counts[table.name] = count
            if connection.dialect.name == "postgresql" and "id" in table.c:
                connection.execute(text(
                    f"SELECT setval(pg_get_serial_sequence(:name, 'id'), "
                    f'COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM "{table.name}"'),
                    {"name": table.name})
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Stopped app's SQLite database backup")
    args = parser.parse_args()
    if engine.dialect.name != "postgresql":
        parser.error("Set DATABASE_URL to the destination PostgreSQL database")
    key = os.getenv("APP_SECRET", "").strip()
    if not key:
        keyfile = DATA / ".app_secret"
        if keyfile.exists():
            key = keyfile.read_text().strip()
    if not key:
        parser.error("Set the original APP_SECRET or restore the original data/.app_secret")
    try:
        cipher = Fernet(key.encode())
        migrate()
        with engine.begin() as connection:
            counts = transfer(args.source, connection, cipher)
    except ValueError as exc:
        parser.exit(1, f"Transfer refused: {exc}\n")
    print("Transfer complete: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    print("Restore the same per-user file storage and encryption key before starting the API.")


if __name__ == "__main__":
    main()
