# Oracle VM: private staging, no email sending

This procedure deploys **v3** as a private preview. It is not a production mail service.
It does not copy v2 data, turn on sending, or expose sign-up on the internet.
You do not need a domain or a Cloudflare account. Only SSH (port 22) is public.
The application binds to the loopback interface of the VM.

## 1. Create your own Oracle Cloud account and VM

1. Sign up in the [Oracle Cloud Console](https://cloud.oracle.com/). Oracle
   does the account verification and receives the payment information directly. Do not
   share account credentials, payment details, API tokens or private SSH keys.
2. In the region that you select, select **Compute > Instances > Create instance**.
   Select an Ubuntu 24.04 image and an **Always Free eligible** shape (for
   example, Ampere A1 Flex, if it is available). A small allocation, such as 1 OCPU
   and 6 GB memory, is sufficient for a private preview. Before you create the VM,
   verify the cost estimate of the console and the eligibility of the boot volume. The availability
   and the Always Free eligibility are different for each region/account.
3. Give the VM a public IPv4 address. For the SSH key, select **Paste public
   keys**, and paste the contents of your `.pub` file. On Windows, if that path does not exist,
   make a dedicated key locally in PowerShell:

   ```powershell
   ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\agnostos_oracle"
   Get-Content "$env:USERPROFILE\.ssh\agnostos_oracle.pub"
   ```

   Keep the private file (without `.pub`) on your own computer. Never paste it
   into the Oracle console or into a chat.
4. In the VCN security list or the network security group of the VM, allow inbound
   TCP **22 only from your current public IP**. Do not open 8000, 5432, 80 or
   443 for this preview. The default network rules of Oracle can allow SSH from
   all addresses. If possible, make them narrower. Record the public IP of the VM.

Connect from PowerShell (replace `VM_IP`):

```powershell
ssh -i "$env:USERPROFILE\.ssh\agnostos_oracle" ubuntu@VM_IP
```

If you selected an image that is not Ubuntu, find the SSH username in its documentation.
Verify the fingerprint of the host key in the Oracle console before you accept it.

## 2. Install Docker and clone v3

On the VM, follow the [Ubuntu installation instructions of Docker](https://docs.docker.com/engine/install/ubuntu/)
for Docker Engine and its Compose plugin. Do not pipe a download that you did not review
directly into a root shell. Make sure that `sudo docker compose version` works.
Then run these commands:

```sh
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/Avinashistoocool/Agnostos-v3.git
cd Agnostos-v3
```

Compose builds the Python API and starts PostgreSQL with persistent Docker
volumes. The database is not mapped to a public port.

## 3. Generate staging secrets and start

Make a separate `.env` **on the VM**. Do not put it in Git or in a chat:

```sh
umask 077
python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
python3 -c 'import secrets; print(secrets.token_hex(32))'
nano .env
```

Write the two generated values into this file:

```dotenv
APP_SECRET=<generated Fernet key; keep this for future restores>
POSTGRES_PASSWORD=<generated hex password>
AGNOSTOS_SCHEDULER_ENABLED=false
AGNOSTOS_LIVE_SEND_ENABLED=false
TZ=Asia/Kolkata
```

Do not include angle brackets, and do not put quotes around the values. Protect the file:
`chmod 600 .env`. Do not copy these items to the VM: your v2 `.env`, mailbox passwords, workbook,
reply queue or Send logs. Keep the optional `cloudflared` Compose
profile off.

```sh
sudo docker compose up -d --build
sudo docker compose ps
curl -fsS http://127.0.0.1:8000/api/health
```

The health endpoint must return `{"ok":true}`. If it does not, examine
`sudo docker compose logs --tail=100 agnostos postgres`, and fix the reported
error. After a successful start, Compose starts the containers again after a reboot.
Verify them again after the VM reboots.

## 4. Open the private preview

In a different **local PowerShell window**, keep this SSH tunnel open:

```powershell
ssh -N -i "$env:USERPROFILE\.ssh\agnostos_oracle" -L 127.0.0.1:8888:127.0.0.1:8000 ubuntu@VM_IP
```

On your computer, go to `http://127.0.0.1:8888/app.html`. Create a **new
staging account**. Use Researchers with disposable test contacts. Make sure that
the banner says that sending is disabled. You can get access to the app only while
your SSH tunnel is open. If a different local process uses port 8888, use a different local
port. Do not change `127.0.0.1:8000` on the right.

## 5. Operate safely

- After updates, check `sudo docker compose ps` and
  `sudo docker compose logs --tail=100 agnostos postgres`.
- To update, run `git pull` in the checkout, then `sudo docker compose up -d --build`.
  Make a backup before changes, because migrations run when the app starts.
- Back up **both** PostgreSQL and the volume of the application files. See
  [database.md](database.md). Keep copies outside the VM, encrypted and with access
  control. Also keep a separate safe copy of `APP_SECRET`.
- Do not enable live sending yet. The legacy CLI of v3 does not have the v2 safeguards for focus, funding,
  address verification and duplicate sends. A PostgreSQL
  contact library that works is not a migration of v2 campaigns or sent history.
- Do not put the v3 app directly on a public hostname yet. Before a public
  launch, do these tasks:
  1. Add an HTTPS/access gateway.
  2. Review signup/authentication.
  3. Implement backups and monitoring.
  4. Complete the v2 feature/safety parity and the campaign migration.

**If you did not create the VM yet:** stop after step 1. To get help with the next step, give only its
public IP and SSH username. Do not share secrets.
