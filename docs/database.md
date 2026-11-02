# Database milestone

## What is database-backed now

Accounts, encrypted user settings, login sessions, job history, schedules and
the new **Researchers** contact library use SQLAlchemy. Docker deployment uses
PostgreSQL 17. Without `DATABASE_URL`, local development retains
`data/agnostos.db` (SQLite); it does not silently copy or discard that file.

The browser's Researchers tab supports create/edit/delete, search, pagination,
and explicit XLSX contact import/export. Imports validate all rows before
writing, skip existing emails rather than overwriting records, and never
approve or send mail. Email-less import duplicates are matched by name and
institution. The import reads the active worksheet with a header in row 1.
Limits: 10 MB uploaded / 40 MB uncompressed / 5,000 rows per import,
10,000 contacts per export. An email is optional; when present it must be
syntactically valid. This is not mailbox verification.

**Still legacy:** Pipeline jobs invoke the CLI and use workbooks; Replies
uses the JSON queue. The Overview statistics describe that legacy pipeline,
not the new contact library. Importing contacts does not migrate drafts,
approvals, sent history or messages. Keep the original data. There is no
automatic sync or implicit handoff to the legacy sender.

## Local preview (no PostgreSQL required)

Install `requirements.txt` and `server/requirements.txt`, then in PowerShell:

```powershell
$env:AGNOSTOS_SCHEDULER_ENABLED = "false"
python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000/app.html`, sign in, and select **Researchers**.
The disabled scheduler does not block manually requested Pipeline jobs:
use only Researchers for a no-send preview.

On startup, Alembic applies additive schema migrations. Existing SQLite
auth/job tables and encrypted data remain intact. Back up `data/` before
upgrading. A standalone migration command is `python -m server.database`.
Do not run schema migrations concurrently.

## PostgreSQL deployment

Set these in the Compose `.env` (not committed):

```dotenv
APP_SECRET=<Fernet key, preserve the original key when upgrading>
POSTGRES_PASSWORD=<long random hex password>
AGNOSTOS_SCHEDULER_ENABLED=false
AGNOSTOS_LIVE_SEND_ENABLED=false
TZ=Asia/Kolkata
```

Generate a new key only for a new installation:
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
Generate a URL-safe database password:
`python -c "import secrets; print(secrets.token_hex(32))"`.

Run `docker compose up -d --build`. PostgreSQL has a health check, is not
published to a host port, and persists in the `postgres-data` volume.
Uploaded files and legacy workspaces persist separately in `agnostos-data`.
Use an HTTPS reverse proxy before exposing the app.

For an external database, set `DATABASE_URL` in the API process environment:
`postgresql+psycopg://user:password@host:5432/agnostos`.
URL-encode special characters in credentials. Plain `postgresql://` URLs
are normalized to the psycopg driver. A direct Python launch reads these
server settings from the process environment, not the CLI `.env` file.

**Run one API process/replica for now.** The existing CLI worker and scheduler
are not a distributed queue. PostgreSQL alone does not make live sending
safe across multiple API workers. Keep schedules disabled while migrating.
The API also refuses `send` and `replies --send` jobs unless
`AGNOSTOS_LIVE_SEND_ENABLED=true` is set deliberately. Keep it false in
staging; the legacy pipeline still lacks v2's safety fixes.

## Move an existing SQLite installation

1. Stop v3's API and all its CLI jobs. Back up the entire `data/` directory.
   This milestone does not touch the separate v2 installation.
2. Provision an empty PostgreSQL database. Set `DATABASE_URL` and the
   **original** `APP_SECRET` in the transfer process environment. The original
   local key is in `data/.app_secret` if you did not supply `APP_SECRET`.
3. Run `python -m server.migrate_sqlite --source <backup-of-agnostos.db>`.
   It refuses non-empty destinations, checks the encryption key, preserves
   IDs and copies rows in one transaction. PostgreSQL ID sequences are reset
   so new accounts/jobs/contacts cannot collide with imported IDs.
4. Restore the original `data/users/` files alongside the API, retain the
   same encryption key, then start with the scheduler disabled. Confirm
   login, settings, job history and file access before considering sending.

The transfer is for v3 accounts/jobs/database contacts. It is not a v2 sent
history migration. No migration starts a mail job.

Back up **both** PostgreSQL (`pg_dump`) and file storage, and protect the
encryption key separately. Never delete volumes as a migration strategy.

## Validation

```powershell
python tests\database_test.py
node --check web\app.js
node --check web\researchers.js
```

The API tests create temporary data and disable scheduling. For PostgreSQL,
set `AGNOSTOS_TEST_DATABASE_URL` to a **disposable** database whose name begins
with `agnostos_test`. The suite clears application tables in that test database.
CI runs the same suite against SQLite and a PostgreSQL service.
The PostgreSQL job also tests importing an existing SQLite account and
verifies that the next generated user ID does not collide.

For the optional browser flow:

```powershell
python -m pip install -r server\requirements-test.txt
python -m playwright install chromium
python tests\researchers_browser_test.py
```

It starts an isolated temporary API, disables scheduling, and exercises the
Researchers page. CDN styling is stubbed for this functional test; it is not
a visual design test.

## Next milestone

Database-backed campaigns, drafts, approval records, messages and send attempts;
a durable worker queue; reconciliation of ambiguous SMTP outcomes; then a
shared React interface and a Tauri desktop client. Do not remove legacy send
history or switch existing campaigns until that migration is verified.
