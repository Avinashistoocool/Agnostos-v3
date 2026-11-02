"""Offline API/storage tests. Use only a disposable agnostos_test* PostgreSQL DB."""
from __future__ import annotations

import io
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
WORK = tempfile.TemporaryDirectory(prefix="agnostos-db-test-")
os.environ["AGNOSTOS_DATA"] = WORK.name
os.environ["AGNOSTOS_SCHEDULER_ENABLED"] = "false"
from cryptography.fernet import Fernet
os.environ["APP_SECRET"] = Fernet.generate_key().decode()
url = os.getenv("AGNOSTOS_TEST_DATABASE_URL", f"sqlite:///{Path(WORK.name).as_posix()}/test.db")
from sqlalchemy.engine import make_url
if not url.startswith("sqlite:") and not (make_url(url).database or "").startswith("agnostos_test"):
    raise RuntimeError("Tests require a disposable PostgreSQL database named agnostos_test*")
os.environ["DATABASE_URL"] = url

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import create_engine, delete, insert, select
from server import database
from server.app import FERNET, _hash, app, load_settings


def xlsx(rows) -> bytes:
    book = Workbook()
    for row in rows:
        book.active.append(row)
    out = io.BytesIO()
    book.save(out)
    book.close()
    return out.getvalue()


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        database.engine.dispose()
        WORK.cleanup()

    def setUp(self):
        with database.engine.begin() as c:
            for table in reversed(database.metadata.sorted_tables):
                c.execute(delete(table))
        self.owner = self.signup("owner@example.org")
        self.other = self.signup("other@example.org")

    def signup(self, email):
        result = self.client.post("/api/signup", json={"email": email, "password": "test-password-123"})
        self.assertEqual(result.status_code, 200, result.text)
        return {"Authorization": f"Bearer {result.json()['token']}"}

    def create(self, **fields):
        response = self.client.post("/api/researchers", headers=self.owner,
                                    json={"name": "Ada", "email": "ada@example.org", **fields})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertNotIn("user_id", response.json())
        return response.json()

    def upload(self, rows, headers=None):
        return self.client.post("/api/researchers/import", headers=headers or self.owner,
                                files={"file": ("contacts.xlsx", xlsx(rows))})

    def test_auth_and_existing_settings_contract(self):
        self.assertEqual(self.client.get("/api/researchers").status_code, 401)
        response = self.client.post("/api/signup", json={
            "email": "OWNER@example.org", "password": "test-password-123"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.post("/api/login", json={
            "email": "owner@example.org", "password": "wrong-password"}).status_code, 401)
        self.assertEqual(self.client.post("/api/login", json={
            "email": "owner@example.org", "password": "test-password-123"}).status_code, 200)
        self.assertEqual(self.client.put("/api/settings", headers=self.owner,
            json={"SMTP_PASSWORD": "private-value", "POSITION": "physics internship"}).status_code, 200)
        me = self.client.get("/api/me", headers=self.owner).json()
        self.assertNotEqual(me["settings"]["SMTP_PASSWORD"], "private-value")
        with database.engine.connect() as c:
            row = c.execute(select(database.users).where(
                database.users.c.email == "owner@example.org")).mappings().one()
        self.assertNotIn(b"private-value", row["settings"])
        self.assertEqual(load_settings(row)["SMTP_PASSWORD"], "private-value")
        for _ in range(2):
            self.assertEqual(self.client.post("/api/waitlist",
                json={"email": "visitor@example.org"}).status_code, 200)
        self.client.post("/api/logout", headers=self.owner)
        self.assertEqual(self.client.get("/api/me", headers=self.owner).status_code, 401)

    def test_crud_isolation_conflicts_and_persistence(self):
        row = self.create(institution="Institute", notes="Keep this")
        self.assertEqual(self.client.get("/api/researchers", headers=self.other).json()["total"], 0)
        edit = {key: row[key] for key in ("name", "email", "institution", "country",
                                         "research_area", "notes", "updated_at")}
        self.assertEqual(self.client.put(f"/api/researchers/{row['id']}",
            headers=self.other, json=edit).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/researchers/{row['id']}",
            headers=self.other, params={"updated_at": row["updated_at"]}).status_code, 404)
        edit["notes"] = "Updated"
        saved = self.client.put(f"/api/researchers/{row['id']}", headers=self.owner, json=edit)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.put(f"/api/researchers/{row['id']}",
            headers=self.owner, json=edit).status_code, 409)
        self.assertEqual(self.client.delete(f"/api/researchers/{row['id']}",
            headers=self.owner, params={"updated_at": row["updated_at"]}).status_code, 409)
        database.engine.dispose()
        self.assertEqual(self.client.get("/api/researchers",
            headers=self.owner).json()["items"][0]["notes"], "Updated")
        self.assertEqual(self.client.delete(f"/api/researchers/{row['id']}",
            headers=self.owner, params={"updated_at": saved.json()["updated_at"]}).status_code, 204)
        self.assertEqual(self.client.get("/api/researchers", headers=self.owner).json()["total"], 0)

    def test_validation_duplicate_email_and_search(self):
        self.create(email="ADA@example.org", research_area="100% physics")
        result = self.client.post("/api/researchers", headers=self.owner,
                                  json={"name": "Another", "email": "ada@example.org"})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.client.post("/api/researchers", headers=self.other,
            json={"name": "Same address, other owner", "email": "ada@example.org"}).status_code, 201)
        for bad in [{"name": " "}, {"name": "A", "email": "not-an-address"},
                    {"name": "A", "user_id": 900}, {"name": "A", "notes": "x" * 5001}]:
            self.assertEqual(self.client.post("/api/researchers",
                headers=self.owner, json=bad).status_code, 422)
        self.create(name="B", email=None)
        self.assertEqual(self.client.get("/api/researchers?q=%25",
            headers=self.owner).json()["total"], 1)
        page = self.client.get("/api/researchers?limit=1&offset=1", headers=self.owner).json()
        self.assertEqual(page["total"], 2)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(self.client.get("/api/researchers?limit=101", headers=self.owner).status_code, 422)

    def test_import_atomic_duplicates_and_export_roundtrip(self):
        rows = [["Professor name", "Email address", "University", "Research area"],
                ["Ada", "ada@example.org", "Institute", "physics"],
                ["Another", "ADA@example.org", "Different", "math"],
                ["No address", "", "Institute", "robotics"]]
        result = self.upload(rows)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["imported"], 2)
        self.assertEqual(result.json()["skipped"], 1)
        again = self.upload(rows).json()
        self.assertEqual((again["imported"], again["skipped"]), (0, 3))
        invalid = self.upload([["Name", "Email"], ["Valid", "valid@example.org"], ["Bad", "invalid"]])
        self.assertEqual(invalid.status_code, 422)
        self.assertIn("Row 3", invalid.text)
        self.assertEqual(self.client.get("/api/researchers", headers=self.owner).json()["total"], 2)
        exported = self.client.get("/api/researchers/export", headers=self.owner)
        self.assertEqual(exported.status_code, 200)
        copy = self.client.post("/api/researchers/import", headers=self.other,
                               files={"file": ("copy.xlsx", exported.content)}).json()
        self.assertEqual(copy["imported"], 2)
        self.assertFalse((Path(WORK.name) / "users" / "1" / "output" / "professors.xlsx").exists())

    def test_bad_workbooks_and_limits(self):
        self.assertEqual(self.client.post("/api/researchers/import", headers=self.owner,
            files={"file": ("bad.xlsx", b"not a workbook")}).status_code, 422)
        self.assertEqual(self.upload([["Wrong header"], ["Ada"]]).status_code, 422)
        self.assertEqual(self.upload([["Name", "Professor"], ["Ada", "Bob"]]).status_code, 422)
        self.assertEqual(self.upload([["Name"]]).status_code, 422)
        from server import researchers as module
        with patch.object(module, "MAX_ROWS", 2):
            self.assertEqual(self.upload([["Name"], ["A"], ["B"], ["C"]]).status_code, 413)
        with patch.object(module, "MAX_UPLOAD", 1):
            self.assertEqual(self.upload([["Name"], ["Ada"]]).status_code, 413)
        self.assertEqual(self.client.get("/api/researchers", headers=self.owner).json()["total"], 0)

    def test_export_treats_formulas_as_text_and_isolates_users(self):
        self.create(name='=HYPERLINK("https://example.org")')
        result = self.client.get("/api/researchers/export", headers=self.owner)
        book = load_workbook(io.BytesIO(result.content))
        self.assertEqual(book.active["A2"].data_type, "s")
        self.assertTrue(book.active["A2"].value.startswith("="))
        book.close()
        other = self.client.get("/api/researchers/export", headers=self.other)
        book = load_workbook(io.BytesIO(other.content))
        self.assertEqual(book.active.max_row, 1)
        book.close()

    def test_jobs_and_schedule_stay_compatible(self):
        with database.engine.begin() as c:
            uid = c.scalar(select(database.users.c.id).where(database.users.c.email == "owner@example.org"))
            c.execute(insert(database.jobs).values(user_id=uid, command="stats", status="done"))
        listed = self.client.get("/api/jobs", headers=self.owner).json()
        self.assertEqual(listed[0]["command"], "stats")
        self.assertEqual(self.client.get("/api/jobs", headers=self.other).json(), [])
        self.assertEqual(self.client.put("/api/schedule", headers=self.owner,
            json={"enabled": False, "time": "08:00", "limit": 20}).status_code, 200)
        self.assertEqual(self.client.get("/api/me", headers=self.owner).json()["schedule"]["limit"], 20)
        self.assertEqual(self.client.post("/api/jobs", headers=self.owner,
            json={"command": "not-allowed"}).status_code, 400)

    def test_private_preview_cannot_send_even_with_direct_api_call(self):
        self.assertFalse(self.client.get("/api/me", headers=self.owner).json()["sending_enabled"])
        for command, options in (("send", {"live": True}), ("send", {"review": True}),
                                 ("send", {}), ("replies", {"send": True, "live": True}),
                                 ("replies", {"send": True})):
            result = self.client.post("/api/jobs", headers=self.owner,
                                      json={"command": command, "options": options})
            self.assertEqual(result.status_code, 403, result.text)
        self.assertEqual(self.client.get("/api/jobs", headers=self.owner).json(), [])
        self.assertEqual(self.client.put("/api/schedule", headers=self.owner,
            json={"enabled": True}).status_code, 403)
        self.assertEqual(self.client.put("/api/schedule", headers=self.owner,
            json={"enabled": False}).status_code, 200)

    def test_upgrade_preserves_legacy_sqlite_accounts(self):
        path = Path(WORK.name) / "legacy.db"
        with closing(sqlite3.connect(path)) as c, c:
            c.execute("""CREATE TABLE users (
                id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL,
                settings BLOB, schedule TEXT, created_at TEXT)""")
            c.execute("INSERT INTO users VALUES (41, ?, ?, ?, NULL, ?)",
                      ("legacy@example.org", _hash("old-password"),
                       FERNET.encrypt(b'{"POSITION":"physics"}'), "2026-10-30"))
        legacy = create_engine(f"sqlite:///{path.as_posix()}")
        try:
            with patch.object(database, "engine", legacy):
                database.migrate()
                database.migrate()
            with legacy.connect() as c:
                row = c.execute(select(database.users)).mappings().one()
                self.assertEqual(row["id"], 41)
                self.assertEqual(load_settings(row)["POSITION"], "physics")
                self.assertEqual(c.execute(select(database.researchers)).all(), [])
        finally:
            legacy.dispose()
            path.unlink()

    def test_explicit_transfer_preserves_ids_and_rejects_nonempty_destination(self):
        from server.migrate_sqlite import transfer
        source = Path(WORK.name) / "transfer-source.db"
        target = create_engine(f"sqlite:///{Path(WORK.name).as_posix()}/transfer-target.db")
        try:
            with closing(sqlite3.connect(source)) as c, c:
                c.execute("""CREATE TABLE users (
                    id INTEGER PRIMARY KEY, email TEXT, pw TEXT, settings BLOB,
                    schedule TEXT, created_at TEXT)""")
                c.execute("INSERT INTO users VALUES (70, ?, ?, ?, NULL, ?)",
                          ("moved@example.org", _hash("test-password"),
                           FERNET.encrypt(b'{"POSITION":"physics"}'), "2026-10-30"))
            database.metadata.create_all(target)
            with self.assertRaisesRegex(ValueError, "original key"):
                with target.begin() as c:
                    transfer(source, c, Fernet(Fernet.generate_key()))
            with target.begin() as c:
                counts = transfer(source, c, FERNET)
                self.assertEqual(counts["users"], 1)
            with target.connect() as c:
                self.assertEqual(c.scalar(select(database.users.c.id)), 70)
            with self.assertRaisesRegex(ValueError, "not empty"):
                with target.begin() as c:
                    transfer(source, c, FERNET)
        finally:
            target.dispose()
            source.unlink()
            (Path(WORK.name) / "transfer-target.db").unlink()

    @unittest.skipUnless(database.engine.dialect.name == "postgresql", "PostgreSQL CI only")
    def test_explicit_transfer_into_postgresql(self):
        from server.migrate_sqlite import transfer
        source = Path(WORK.name) / "transfer-postgres.db"
        try:
            with closing(sqlite3.connect(source)) as c, c:
                c.execute("""CREATE TABLE users (
                    id INTEGER PRIMARY KEY, email TEXT, pw TEXT, settings BLOB,
                    schedule TEXT, created_at TEXT)""")
                c.execute("INSERT INTO users VALUES (70, ?, ?, ?, NULL, ?)",
                          ("moved@example.org", _hash("test-password"),
                           FERNET.encrypt(b'{"POSITION":"physics"}'), "2026-10-30"))
            # setUp creates two accounts. Remove them in the same transaction:
            # a failure rolls back both the removal and partial transfer.
            with database.engine.begin() as c:
                c.execute(delete(database.sessions))
                c.execute(delete(database.users))
                counts = transfer(source, c, FERNET)
                self.assertEqual(counts["users"], 1)
                self.assertEqual(c.scalar(select(database.users.c.id)), 70)
            with database.engine.begin() as c:
                next_id = c.execute(insert(database.users).values(
                    email="next@example.org", pw="irrelevant").returning(database.users.c.id)).scalar_one()
                self.assertGreater(next_id, 70)
        finally:
            source.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
