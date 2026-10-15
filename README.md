# Agnostos v3

Agnostos is a web app built on the Agnostos outreach pipeline. Each user signs up, uploads a resume, and connects their own mailbox and model key. From the browser they can discover professors, verify emails, draft, send, read replies and send follow-ups. The landing page uses a soft visual theme.

```
web/         landing page (index.html) and dashboard (app.html), static, no build step
server/      FastAPI: auth, per-user workspaces, encrypted credentials, job runner, daily scheduler
outreach/    the CLI pipeline, unchanged; each job runs it as a subprocess
```

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
- The scheduler runs a paced send on weekdays for every user who turns it on.

## Deploying for free

The app needs **a process that stays up for hours**, because a paced send of 40 emails takes 4 to 7 hours. It also needs **a persistent disk** and **outbound SMTP on port 465 or 587**. That rules out serverless hosts and the free tiers of hosts that sleep (Vercel, Netlify, Render free, Railway trial).

| Option | Cost | Good for | Notes |
|---|---|---|---|
| **Oracle Cloud Always Free** ARM VM (4 vCPU / 24 GB) + Cloudflare Tunnel | $0 | **Recommended** for real users | Always on, 200 GB disk, outbound 465/587 allowed. |
| Google Cloud e2-micro (always free) + Cloudflare Tunnel | $0 | small, a few users | 1 GB RAM: add swap. |
| Your own laptop or PC + Tailscale Funnel / Cloudflare Tunnel | $0 | you and friends | Only up while the machine is awake. |
| Hugging Face Spaces (Docker) | $0 | demo only | Sleeps when idle and has no free persistent disk, so it can lose jobs. |

You do **not** need a separate frontend host: FastAPI serves `web/`. If you want the landing page on a CDN anyway, point Cloudflare Pages at `web/`. The `/app.html` and `/api` routes still have to reach the VM.

### Oracle Cloud and Cloudflare Tunnel, step by step

1. Create an Oracle Cloud account and an **Ampere A1** instance (Ubuntu 24.04, 2-4 OCPU, 12-24 GB).
2. SSH in and install Docker:
   `curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker $USER`
3. `git clone https://github.com/<you>/Agnostos-v3 && cd Agnostos-v3`
4. Create `.env` next to `docker-compose.yml`:
   ```
   APP_SECRET=<python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())">
   TZ=Asia/Kolkata
   CLOUDFLARE_TUNNEL_TOKEN=<from Cloudflare Zero Trust -> Networks -> Tunnels -> Create>
   ```
   In the tunnel's *Public hostname* settings, map `agnostos.<your-domain>` to `http://agnostos:8000`. A free domain from Cloudflare Registrar at cost is fine, and so is a free `*.trycloudflare.com` quick tunnel for testing.
5. `docker compose --profile tunnel up -d --build`
6. Back up `/data` (it holds the database, the secret and every user's files):
   `docker run --rm -v agnostos_agnostos-data:/d -v $PWD:/b alpine tar czf /b/backup.tgz /d`

Nothing listens on a public port, because the tunnel connects outbound. HTTPS comes from Cloudflare.

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
- Every user's jobs run on one machine. On the free Oracle VM, about 20-50 concurrent paced senders is comfortable, because they mostly sleep between emails.
- Users' mailbox passwords are stored on your server. Use a strong `APP_SECRET`, keep backups encrypted, and publish a privacy note.
