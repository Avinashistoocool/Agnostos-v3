# Database milestone

## What is database-backed now

Accounts, encrypted user settings, login sessions, job history, schedules and
the new **Researchers** contact library use SQLAlchemy. The Docker deployment uses
PostgreSQL 17. Without `DATABASE_URL`, local development keeps
`data/agnostos.db` (SQLite). It does not copy or discard that file without a message.

The Researchers tab of the browser has these functions: create/edit/delete, search, pagination,
and explicit XLSX import/export of contacts. Imports validate all rows before
they write. They skip existing emails, and do not overwrite records. They never
approve or send mail. For imported duplicates without an email, the import compares the name and
the institution. The import reads the active worksheet, with a header in row 1.
Limits: 10 MB uploaded / 40 MB uncompressed / 5,000 rows for each import,
10,000 contacts for each export. An email is optional. If there is an email, its syntax must be
correct. This is not a verification of the mailbox.

**Still legacy:** Pipeline jobs run the CLI and use workbooks. Replies
uses the JSON queue. The Overview statistics describe that legacy pipeline,
not the new contact library. An import of contacts does not move drafts,
approvals, sent history or messages. Keep the original data. There is no
automatic synchronisation, and the legacy sender does not get the contacts implicitly.

## Local preview (no PostgreSQL required)

Install `requirements.txt` and `server/requirements.txt`. Then, in PowerShell, run:

```powershell
$env:AGNOSTOS_SCHEDULER_ENABLED = "false"
python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000/app.html`, sign in, and select **Researchers**.
The disabled scheduler does not block Pipeline jobs that you start manually.
For a preview that sends nothing, use only Researchers.

At startup, Alembic applies additive schema migrations. The existing SQLite
auth/job tables and the encrypted data do not change. Back up `data/` before
the upgrade. The standalone migration command is `python -m server.database`.
Do not run two schema migrations at the same time.

## PostgreSQL deployment

Set these values in the Compose `.env` (do not commit it):

```dotenv
APP_SECRET=<Fernet key, preserve the original key when upgrading>
POSTGRES_PASSWORD=<long random hex password>
AGNOSTOS_SCHEDULER_ENABLED=false
AGNOSTOS_LIVE_SEND_ENABLED=false
TZ=Asia/Kolkata
```

Make a new key only for a new installation:
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
Make a URL-safe database password:
`python -c "import secrets; print(secrets.token_hex(32))"`.

Run `docker compose up -d --build`. PostgreSQL has a health check. It is not
published to a host port, and its data stays in the `postgres-data` volume.
Uploaded files and legacy workspaces stay separately in `agnostos-data`.
Use an HTTPS reverse proxy before you expose the app.

For an external database, set `DATABASE_URL` in the environment of the API process:
`postgresql+psycopg://user:password@host:5432/agnostos`.
Use URL encoding for special characters in credentials. The app changes plain `postgresql://` URLs
to the psycopg driver. If you start Python directly, it reads these
server settings from the process environment, not from the CLI `.env` file.

**At this time, run only one API process/replica.** The existing CLI worker and scheduler
are not a distributed queue. PostgreSQL alone does not make live sending
safe across more than one API worker. Keep schedules disabled during the migration.
The API also refuses `send` and `replies --send` jobs, unless you intentionally set
`AGNOSTOS_LIVE_SEND_ENABLED=true`. Keep it false in
staging, because the legacy pipeline does not have the safety fixes of v2.

## Move an existing SQLite installation

1. Stop the v3 API and all its CLI jobs. Back up the full `data/` directory.
   This milestone does not change the separate v2 installation.
2. Prepare an empty PostgreSQL database. In the environment of the transfer process, set `DATABASE_URL` and the
   **original** `APP_SECRET`. If you did not supply `APP_SECRET`, the original
   local key is in `data/.app_secret`.
3. Run `python -m server.migrate_sqlite --source <backup-of-agnostos.db>`.
   The command refuses destinations that are not empty. It checks the encryption key, keeps the
   IDs, and copies the rows in one transaction. It resets the PostgreSQL ID sequences,
   so that new accounts/jobs/contacts cannot have the same IDs as imported rows.
4. Put the original `data/users/` files back next to the API, and keep the
   same encryption key. Then start with the scheduler disabled. Make sure that
   login, settings, job history and file access work before you think about sending.

The transfer is for v3 accounts/jobs/database contacts. It does not move the v2 sent
history. No migration starts a mail job.

Back up **both** PostgreSQL (`pg_dump`) and the file storage. Protect the
encryption key separately. Never delete volumes as a migration method.

## Validation

```powershell
python tests\database_test.py
node --check web\app.js
node --check web\researchers.js
```

The API tests make temporary data and disable the scheduler. For PostgreSQL,
set `AGNOSTOS_TEST_DATABASE_URL` to a **disposable** database with a name that starts
with `agnostos_test`. The suite clears the application tables in that test database.
CI runs the same suite with SQLite and with a PostgreSQL service.
The PostgreSQL job also tests the import of an existing SQLite account. It
makes sure that the next generated user ID is not the same as an existing ID.

For the optional browser flow, run these commands:

```powershell
python -m pip install -r server\requirements-test.txt
python -m playwright install chromium
python tests\researchers_browser_test.py
```

The test starts an isolated temporary API, disables the scheduler, and tests the
Researchers page. The test replaces the CDN styles with a stub. It is a functional test, not
a test of the visual design.

## Next milestone

The next milestone has these items:

1. Campaigns, drafts, approval records, messages and send attempts in the database.
2. A durable worker queue.
3. Reconciliation of SMTP results that are not clear.
4. Then a shared React interface and a Tauri desktop client.

Do not remove the legacy send history, and do not change existing campaigns, until you verify that migration.
