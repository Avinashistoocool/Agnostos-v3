"""Shared relational storage for the API, independent of the legacy CLI."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import (
    Column, Float, ForeignKey, Index, Integer, LargeBinary, MetaData, Table,
    Text, UniqueConstraint, create_engine, event,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("AGNOSTOS_DATA", ROOT / "data")).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA / 'agnostos.db').as_posix()}")
if DATABASE_URL.startswith(("postgres://", "postgresql://")):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.split("://", 1)[1]

engine = create_engine(
    DATABASE_URL, pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 30}
    if DATABASE_URL.startswith("sqlite:") else {},
)
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _sqlite_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

metadata = MetaData()
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("email", Text, nullable=False, unique=True),
    Column("pw", Text, nullable=False),
    Column("settings", LargeBinary),
    Column("schedule", Text),
    Column("created_at", Text),
)
sessions = Table(
    "sessions", metadata,
    Column("token", Text, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("created_at", Float),
)
jobs = Table(
    "jobs", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("command", Text), Column("args", Text), Column("status", Text),
    Column("pid", Integer), Column("started_at", Text),
    Column("finished_at", Text), Column("exit_code", Integer),
)
waitlist = Table(
    "waitlist", metadata,
    Column("email", Text, primary_key=True), Column("created_at", Text),
)
researchers = Table(
    "researchers", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("email", Text),
    Column("institution", Text, nullable=False, default=""),
    Column("country", Text, nullable=False, default=""),
    Column("research_area", Text, nullable=False, default=""),
    Column("notes", Text, nullable=False, default=""),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    UniqueConstraint("user_id", "email", name="uq_researchers_user_email"),
)
Index("ix_researchers_user_id", researchers.c.user_id, researchers.c.id)


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(ROOT / "server" / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


if __name__ == "__main__":
    migrate()
    print(f"Database migrations complete ({engine.dialect.name}).")
