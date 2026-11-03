# Agnostos: research internship outreach web app

**Agnostos** is a web app built on the [Agnostos outreach pipeline](https://github.com/Avinashistoocool/Agnostos-v2). Each user signs up, uploads a resume, and connects their own mailbox and model key. From the browser they can discover professors, verify emails, draft, send, read replies and send follow-ups. The landing page uses a soft visual theme.

```
web/         landing page and dashboard, bundled CSS/fonts (compiled CSS checked in)
server/      FastAPI: auth, per-user workspaces, encrypted credentials, job runner, daily scheduler
outreach/    the CLI pipeline, unchanged; each job runs it as a subprocess
```

## Database-first milestone

The **Researchers** tab is now a database-backed contact library: add/edit/delete,
search, pagination, XLSX import and export. Accounts, settings and job history
also use the shared SQLAlchemy storage layer with Alembic migrations.
Docker Compose provisions PostgreSQL; local development keeps existing SQLite
data unless `DATABASE_URL` is explicitly set.

**Pipeline sending and reply queues are still legacy.** The contact library
does not automatically feed the sender, and imports never approve messages.
See [database setup, migration and limitations](docs/database.md) before moving
existing data. A local Windows desktop preview is available below.

## Windows desktop preview

Install Python 3.13 (64-bit) and Microsoft Edge WebView2 Runtime on Windows.
In PowerShell, from this repository:

```powershell
py -3.13 -m pip install -r desktop-requirements.txt
py -3.13 desktop.py
```

To build a distributable folder, install Node.js/npm for the stylesheet build.
Run `.\build-desktop.ps1 -Python "py"` only if
`py` resolves to the intended Python interpreter, or use:

```powershell
.\build-desktop.ps1 -Python "C:\Path\To\Python313\python.exe"
.\dist\Agnostos\Agnostos.exe --health-check
.\dist\Agnostos\Agnostos.exe
```

For the automated HTTP and browser flow check, run
`py -3.13 -m unittest discover -s tests -p desktop_test.py` after installing
Playwright and its Chromium browser (`py -3.13 -m playwright install chromium`).
If startup fails, inspect `%LOCALAPPDATA%\Agnostos\startup-error.log`.
The build script runs `npm ci` and compiles `web\site.css` from
`web\tailwind.css` and `tailwind.config.js`. When editing interface classes,
run `npm ci; npm run build:css` and keep the generated CSS in sync.

Distribute **the whole `dist\Agnostos` folder**, not just the executable.
The packaged app does not require Python on the destination PC; WebView2
Runtime is required. Close the window to stop the loopback server. The first
launch creates `%LOCALAPPDATA%\Agnostos\` with its own SQLite database,
encryption key, uploads and job output. Back up that directory together;
deleting its `.app_secret` makes encrypted settings unreadable. No existing
v2 files, credentials or databases are copied. The build allowlists web assets
and migration source files, and rejects distributions containing `.env`,
`.app_secret` or `.db` files. It does not package the repository `.env` or
per-user data.

The desktop server binds only to `127.0.0.1` on a random port; sending and
the send scheduler are disabled regardless of inherited environment settings.
It is a **private preview, not v2 safety parity**: database contacts do not
feed the pipeline and drafts do not gain any new approval guarantees. Signup
is still required, and other processes on the same PC can reach the local
HTTP service while the window is open. Both dashboard and landing-page styles
and fonts are bundled and work offline; discovery, model and mail features
still need internet. The bundled fonts are distributed under their OFL notices
in `web\fonts\`. Do not expose the port or use it for live campaigns.

## SEO checklist (to rank first for "agnostos")

The page already has the on-page signals: keyword title/description, canonical URL, Open Graph and Twitter cards, `og.png`, Organization/WebSite/SoftwareApplication/FAQPage JSON-LD, FAQ text crawlers can read, `robots.txt`, `sitemap.xml` and a `noindex` on the dashboard.

The rest has to be done off the page:

1. **Domain.** Buy one with the brand name in it (e.g. `agnostos.app`). If you choose a different domain, find and replace `https://agnostos.app` in `web/index.html`, `web/robots.txt` and `web/sitemap.xml`.
2. **Deploy** (see below) so it's live over HTTPS.
3. **Google Search Console**: add the domain, verify it via DNS TXT, submit `/sitemap.xml`, and use *URL Inspection → Request indexing*. Do the same in **Bing Webmaster Tools** (which also feeds DuckDuckGo and Yahoo).
4. **Backlinks with the anchor text "Agnostos"**: the GitHub repo homepage fields, your GitHub profile README, LinkedIn, a Product Hunt launch, a Show HN post, Reddit (r/gradadmissions, r/PhD), dev.to/Medium write-ups, and your personal or college pages.
5. **Consistent naming**: use "Agnostos" (not "agnostos-v2") as the name everywhere you link it.

Expect indexing within days. Ranking first for a rare brand word usually takes 1–4 weeks once there are a handful of backlinks.

## Run it locally

```
start.cmd          # Windows
./start.sh         # macOS / Linux
```

Then open http://localhost:8000.

## How it works

- Each user's credentials (SMTP/IMAP passwords, API keys) are encrypted with Fernet using `APP_SECRET` and are only passed into that user's job environment.
- Jobs come from an allow-list of commands and flags. Request values are type-checked, so no raw arguments reach the shell.
- Each user's files live in `/data/users/<id>/`. Job logs stream to the dashboard.
- In the legacy server configuration only, the scheduler can run paced sends
  for opted-in users. The desktop preview forcibly disables this scheduler.

## Deployment

**Hosted deployment is paused.** The following describes an older, optional
server staging plan, not the recommended way to run the desktop preview.

**Previous plan: [private Oracle VM staging](docs/oracle-private-staging.md).**
It runs v3 + PostgreSQL on a VM, keeps the web app bound to localhost, and
connects over an SSH tunnel. No domain is needed. Sending is disabled by
default; v2 outreach remains on your computer. **Do not expose v3 as a public
mail service until v2 feature/safety parity and campaign migration are done.**

The app needs **a process that stays up for hours**, because a paced send of 40 emails takes 4 to 7 hours. It also needs **a persistent disk** and **outbound SMTP on port 465 or 587**. That rules out serverless hosts and the free tiers of hosts that sleep (Vercel, Netlify, Render free, Railway trial).

| Option | Cost | Good for | Notes |
|---|---|---|---|
| **Oracle Cloud Always Free eligible** ARM VM | Check console eligibility | Private v3 staging | Availability varies; outbound mail ports are not guaranteed and are irrelevant while sending is off. |
| Google Cloud e2-micro (always free) + Cloudflare Tunnel | $0 | small, a few users | 1 GB RAM: add swap. |
| Your own laptop or PC + Tailscale Funnel / Cloudflare Tunnel | $0 | you and friends | Only up while the machine is awake. |
| Hugging Face Spaces (Docker) | $0 | demo only | Sleeps when idle and has no free persistent disk, so it can lose jobs. |

You do **not** need a separate frontend host: FastAPI serves `web/`. If you want the landing page on a CDN anyway, point Cloudflare Pages at `web/`. The `/app.html` and `/api` routes still have to reach the VM.

The [Oracle private staging guide](docs/oracle-private-staging.md) and optional
Cloudflare Tunnel profile are historical plans. Do not enable either for the
desktop preview.

### Your own machine, with Tailscale

```
start.cmd
tailscale funnel 8000        # public https://<machine>.<tailnet>.ts.net
```

## What each user needs to bring

- **A model key.** A Groq key is free. OpenAI `gpt-5-mini` costs about $0.004 per draft.
- **A mailbox with an app password.** For Gmail, turn on 2FA and then create an app password. University mail usually works with SMTP over SSL on port 465.
- **A resume** (PDF or DOCX), and optionally a CV PDF to attach.

## Limits to know before inviting people

- Each user sends from **their own** mailbox, so deliverability and rate limits are per user. Keep `DAILY_SEND_CAP` at or below 40.
- Every user's jobs run on one machine; capacity depends on the VM and workload.
- Users' mailbox passwords are stored on your server. Use a strong `APP_SECRET`, keep backups encrypted, and publish a privacy note.
