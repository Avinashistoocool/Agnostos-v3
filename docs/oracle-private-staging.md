# Oracle VM: private staging, no email sending

This deploys **v3** as a private preview, not a production mail service.
It does not copy v2 data, turn on sending, or expose sign-up on the internet.
No domain or Cloudflare account is required. Only SSH (port 22) is public;
the application binds to the VM's loopback interface.

## 1. Create your own Oracle Cloud account and VM

1. Sign up in the [Oracle Cloud Console](https://cloud.oracle.com/). Oracle
   handles account verification and any payment information directly; do not
   share account credentials, payment details, API tokens or private SSH keys.
2. In your chosen region, select **Compute > Instances > Create instance**.
   Choose an Ubuntu 24.04 image and an **Always Free eligible** shape (for
   example Ampere A1 Flex, if available). A modest allocation such as 1 OCPU
   and 6 GB memory is sufficient for a private preview. Verify the console's
   cost estimate and boot-volume eligibility before creating it. Availability
   and Always Free eligibility vary by region/account.
3. Give the VM a public IPv4 address. For the SSH key, select **Paste public
   keys** and paste the contents of your `.pub` file. On Windows, generate
   a dedicated key locally in PowerShell, if that path does not already exist:

   ```powershell
   ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\agnostos_oracle"
   Get-Content "$env:USERPROFILE\.ssh\agnostos_oracle.pub"
   ```

   Keep the private file without `.pub` on your own computer; never paste it
   into the Oracle console or a chat.
4. In the VM's VCN security list or network security group, allow inbound
   TCP **22 from your current public IP only**. Do not open 8000, 5432, 80 or
   443 for this preview. Oracle's default network rules may allow SSH from
   everywhere; narrow them where possible. Record the VM's public IP.

Connect from PowerShell (replace `VM_IP`):

```powershell
ssh -i "$env:USERPROFILE\.ssh\agnostos_oracle" ubuntu@VM_IP
```

If you chose an image other than Ubuntu, check its documented SSH username.
Verify the host key fingerprint in the Oracle console before accepting it.

## 2. Install Docker and clone v3

On the VM, follow [Docker's Ubuntu installation instructions](https://docs.docker.com/engine/install/ubuntu/)
for Docker Engine and its Compose plugin. Do not pipe an unreviewed download
directly into a root shell. Confirm `sudo docker compose version` works.
Then:

```sh
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/Avinashistoocool/Agnostos-v3.git
cd Agnostos-v3
```

Compose builds the Python API and starts PostgreSQL with persistent Docker
volumes. The database is not mapped to any public port.

## 3. Generate staging secrets and start

Create a separate `.env` **on the VM**, not in Git or chat:

```sh
umask 077
python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
python3 -c 'import secrets; print(secrets.token_hex(32))'
nano .env
```

Enter the two generated values into this file:

```dotenv
APP_SECRET=<generated Fernet key; keep this for future restores>
POSTGRES_PASSWORD=<generated hex password>
AGNOSTOS_SCHEDULER_ENABLED=false
AGNOSTOS_LIVE_SEND_ENABLED=false
TZ=Asia/Kolkata
```

Do not include angle brackets or quote the values. Protect the file:
`chmod 600 .env`. Do not copy your v2 `.env`, mailbox passwords, workbook,
reply queue or Send logs to the VM. Leave the optional `cloudflared` Compose
profile off.

```sh
sudo docker compose up -d --build
sudo docker compose ps
curl -fsS http://127.0.0.1:8000/api/health
```

The health endpoint should return `{"ok":true}`. If it does not, check
`sudo docker compose logs --tail=100 agnostos postgres` and fix the reported
error. After a successful startup, Compose restarts containers on reboot;
verify them again after the VM reboots.

## 4. Open the private preview

In another **local PowerShell window**, keep this SSH tunnel running:

```powershell
ssh -N -i "$env:USERPROFILE\.ssh\agnostos_oracle" -L 127.0.0.1:8888:127.0.0.1:8000 ubuntu@VM_IP
```

Visit `http://127.0.0.1:8888/app.html` on your computer. Create a **new
staging account**, use Researchers with disposable test contacts, and check
the banner that says sending is disabled. The app is accessible only while
your SSH tunnel is open. If port 8888 is taken locally, use another local
port; keep `127.0.0.1:8000` on the right unchanged.

## 5. Operate safely

- Check `sudo docker compose ps` and
  `sudo docker compose logs --tail=100 agnostos postgres` after updates.
- Run `git pull` inside the checkout, then `sudo docker compose up -d --build`.
  Back up before changes; migrations run on app startup.
- Back up **both** PostgreSQL and the application file volume. See
  [database.md](database.md). Keep copies off the VM, encrypted and access
  controlled, along with a separate safe copy of `APP_SECRET`.
- Do not enable live sending yet: v3's legacy CLI lacks v2's focus, funding,
  address-verification and duplicate-send safeguards. A functional PostgreSQL
  contact library is not a migration of v2 campaigns or sent history.
- Do not put v3's app directly on a public hostname yet. Before a public
  launch, add an HTTPS/access gateway, review signup/authentication,
  implement backups and monitoring, and finish the v2 feature/safety parity
  and campaign migration.

**If the VM is not yet created:** stop after step 1 and provide only its
public IP and SSH username for help with the next step. Do not share secrets.
