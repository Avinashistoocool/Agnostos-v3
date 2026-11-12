# Agnostos: research internship outreach web app

**Agnostos** is a web app that uses the [Agnostos outreach pipeline](https://github.com/Avinashistoocool/Agnostos-v2). Each user makes an account, uploads a resume, and connects their own mailbox and model key. In the browser, the user can do these tasks:

- discover professors
- verify emails
- write drafts and send them
- read replies and send follow-ups.

The landing page uses a soft visual theme.

```
web/         landing page and dashboard, bundled CSS/fonts (compiled CSS checked in)
server/      FastAPI: auth, per-user workspaces, encrypted credentials, job runner, daily scheduler
outreach/    the CLI pipeline, unchanged; each job runs it as a subprocess
```

## Database-first milestone

The **Researchers** tab is now a contact library in a database. It has these functions:
add/edit/delete, search, pagination, XLSX import and export. Accounts, settings and job history
also use the shared SQLAlchemy storage layer with Alembic migrations.
Docker Compose supplies PostgreSQL. Local development keeps the existing SQLite
data, unless you set `DATABASE_URL` explicitly.

**Pipeline sending and reply queues are still legacy.** The contact library
does not automatically supply contacts to the sender, and imports never approve messages.
Before you move existing data, read [database setup, migration and limitations](docs/database.md).
A local Windows desktop preview is available below.

## Windows desktop preview

Install Python 3.13 (64-bit) and Microsoft Edge WebView2 Runtime on Windows.
In PowerShell, from this repository, run these commands:

```powershell
py -3.13 -m pip install -r desktop-requirements.txt
py -3.13 desktop.py
```

To build a folder for distribution, install Node.js/npm for the stylesheet build.
Run `.\build-desktop.ps1 -Python "py"` only if
`py` points to the correct Python interpreter. Alternatively, use these commands:

```powershell
.\build-desktop.ps1 -Python "C:\Path\To\Python313\python.exe"
.\dist\Agnostos\Agnostos.exe --health-check
.\dist\Agnostos\Agnostos.exe
```

To check the HTTP and browser flow automatically, install
Playwright and its Chromium browser (`py -3.13 -m playwright install chromium`). Then run
`py -3.13 -m unittest discover -s tests -p desktop_test.py`.
If the application does not start, examine `%LOCALAPPDATA%\Agnostos\startup-error.log`.
The build script runs `npm ci`, and it compiles `web\site.css` from
`web\tailwind.css` and `tailwind.config.js`. When you edit interface classes,
run `npm ci; npm run build:css`, and keep the generated CSS up to date.

Distribute **the full `dist\Agnostos` folder**, not only the executable.
Alternatively, open GitHub **Actions → Windows desktop → a successful run →
Artifacts → Agnostos-Windows**. There you can download the zipped build from `main`
(or run the workflow manually). Extract the artifact, and keep `Agnostos.exe`
next to `_internal\`. Artifacts expire after 14 days. They are not public
installer releases. Before the upload, the workflow runs offline browser tests and
`.\tests\check-desktop-package.ps1`.

The packaged app does not need Python on the destination PC, but it needs the WebView2
Runtime. To stop the loopback server, close the window. The first
start makes `%LOCALAPPDATA%\Agnostos\`, with its own SQLite database,
encryption key, uploads and job output. Back up all of that directory at the same time.
If you delete its `.app_secret`, the app cannot read the encrypted settings. The app copies no existing
v2 files, credentials or databases. The build accepts only listed web assets
and migration source files. It rejects distributions that contain `.env`,
`.app_secret` or `.db` files. It does not package the `.env` of the repository or
the data of users.

The desktop server binds only to `127.0.0.1` on a random port. Sending and
the send scheduler are disabled, whatever the inherited environment settings are.
It is a **private preview, not v2 safety parity**. Database contacts do not
go to the pipeline, and drafts do not get new approval guarantees. Users must
still sign up. While the window is open, other processes on the same PC can connect to the local
HTTP service. The styles and fonts of the dashboard and of the landing page
are bundled, and they work offline. Discovery, model and mail functions
still need internet. The bundled fonts are distributed under their OFL notices
in `web\fonts\`. Do not expose the port, and do not use it for live campaigns.

## SEO checklist (to rank first for "agnostos")

The page already has the on-page signals. These signals are:

- a title and a description with the keyword, and a canonical URL
- Open Graph and Twitter cards, and `og.png`
- Organization/WebSite/SoftwareApplication/FAQPage JSON-LD
- FAQ text that crawlers can read
- `robots.txt`, `sitemap.xml`, and a `noindex` on the dashboard.

You must do the remaining tasks outside the page:

1. **Domain.** Buy a domain that contains the brand name (for example, `agnostos.app`). If you select a different domain, find and replace `https://agnostos.app` in `web/index.html`, `web/robots.txt` and `web/sitemap.xml`.
2. **Deploy** the app (see below), so that it is live over HTTPS.
3. **Google Search Console**: add the domain, and verify it through a DNS TXT record. Submit `/sitemap.xml`, and use *URL Inspection → Request indexing*. Do the same in **Bing Webmaster Tools** (it also supplies DuckDuckGo and Yahoo).
4. **Backlinks with the anchor text "Agnostos"**: put links in these locations:
   - the homepage fields of the GitHub repository, and your GitHub profile README
   - LinkedIn, a Product Hunt launch, and a Show HN post
   - Reddit (r/gradadmissions, r/PhD) and dev.to/Medium articles
   - your personal pages or college pages.
5. **Consistent naming**: in all your links, use the name "Agnostos" (not "agnostos-v2").

Indexing usually occurs within days. When there are some backlinks, the first rank for a rare brand word usually takes 1–4 weeks.

## Run it locally

```
start.cmd          # Windows
./start.sh         # macOS / Linux
```

Then open http://localhost:8000.

## How it works

- The app encrypts the credentials of each user (SMTP/IMAP passwords, API keys) with Fernet and `APP_SECRET`. It gives them only to the job environment of that user.
- Jobs come from an allow-list of commands and flags. The app checks the type of each request value. Thus, no raw arguments get to the shell.
- The files of each user are in `/data/users/<id>/`. Job logs stream to the dashboard.
- Only in the legacy server configuration, the scheduler can run sends at intervals
  for users who opted in. The desktop preview always disables this scheduler.

## Deployment

**Hosted deployment is paused.** The text below describes an older, optional
plan for server staging. It is not the recommended method to run the desktop preview.

**Previous plan: [private Oracle VM staging](docs/oracle-private-staging.md).**
In this plan, v3 + PostgreSQL run on a VM. The web app binds only to localhost, and you
connect over an SSH tunnel. You do not need a domain. Sending is disabled by
default, and v2 outreach stays on your computer. **Do not expose v3 as a public
mail service until v2 feature/safety parity and the campaign migration are complete.**

The app needs **a process that stays active for hours**, because a send of 40 emails at intervals takes 4 to 7 hours. It also needs **a persistent disk** and **outbound SMTP on port 465 or 587**. Thus, you cannot use serverless hosts, or the free tiers of hosts that go to sleep (Vercel, Netlify, Render free, Railway trial).

| Option | Cost | Good for | Notes |
|---|---|---|---|
| **Oracle Cloud Always Free eligible** ARM VM | Check the eligibility in the console | Private v3 staging | The availability changes. Outbound mail ports are not guaranteed, and they are not important while sending is off. |
| Google Cloud e2-micro (always free) + Cloudflare Tunnel | $0 | small, a few users | 1 GB RAM: add swap. |
| Your own laptop or PC + Tailscale Funnel / Cloudflare Tunnel | $0 | you and friends | Available only while the machine is awake. |
| Hugging Face Spaces (Docker) | $0 | demo only | Goes to sleep when idle, and has no free persistent disk. Thus, it can lose jobs. |

You do **not** need a separate frontend host, because FastAPI serves `web/`. If you want the landing page on a CDN, point Cloudflare Pages to `web/`. The `/app.html` and `/api` routes must still get to the VM.

The [Oracle private staging guide](docs/oracle-private-staging.md) and the optional
Cloudflare Tunnel profile are old plans. Do not enable them for the
desktop preview.

### Your own machine, with Tailscale

```
start.cmd
tailscale funnel 8000        # public https://<machine>.<tailnet>.ts.net
```

## What each user needs to bring

- **A model key.** A Groq key is free. OpenAI `gpt-5-mini` costs about $0.004 for each draft.
- **A mailbox with an app password.** For Gmail, turn on 2FA, and then make an app password. University mail usually works with SMTP over SSL on port 465.
- **A resume** (PDF or DOCX). Optionally, a CV PDF to attach.

## Limits to know before inviting people

- Each user sends from **their own** mailbox. Thus, deliverability and rate limits apply to each user separately. Keep `DAILY_SEND_CAP` at 40 or less.
- The jobs of all users run on one machine. The capacity depends on the VM and the workload.
- Your server stores the mailbox passwords of the users. Use a strong `APP_SECRET`, keep the backups encrypted, and publish a privacy note.
