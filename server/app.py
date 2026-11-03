"""Agnostos web: multi-user API around the outreach CLI.

Each user gets an isolated workspace (uploads, output/, logs). Their SMTP /
IMAP / LLM credentials are encrypted at rest and only ever handed to the CLI
subprocess through its environment, so the pipeline code is reused unchanged.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from .database import DATA, ROOT, engine, jobs, migrate, sessions, users, waitlist as waitlist_table


def _fernet() -> Fernet:
    key = os.getenv("APP_SECRET", "").strip()
    keyfile = DATA / ".app_secret"
    if not key:
        if not keyfile.exists():
            keyfile.write_text(Fernet.generate_key().decode())
        key = keyfile.read_text().strip()
    return Fernet(key.encode())


FERNET = _fernet()

# Settings a user may set; everything else stays server-controlled.
USER_KEYS = {
    "LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_BASE_URL", "GROQ_API_KEY", "DRAFT_MODEL",
    "BUDGET_USD", "MAX_PROFESSORS", "MIN_LOCAL_SCORE",
    "POSITION", "GEOGRAPHY", "AVAILABILITY",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_SECURITY",
    "SMTP_FROM", "SMTP_FROM_NAME", "REPLY_TO",
    "IMAP_HOST", "IMAP_PORT", "IMAP_USER", "IMAP_PASSWORD",
    "SEND_DELAY_MIN", "SEND_DELAY_MAX", "DAILY_SEND_CAP", "SEND_LOCAL_WINDOW",
    "DISCOVER_QUERIES", "DISCOVER_COUNTRIES", "OPENALEX_MAILTO",
}
SECRET_KEYS = {"OPENAI_API_KEY", "GROQ_API_KEY", "SMTP_PASSWORD", "IMAP_PASSWORD"}


def sending_enabled() -> bool:
    return os.getenv("AGNOSTOS_LIVE_SEND_ENABLED", "false").strip().lower() == "true"


# Every command the UI can run, and the flags it may pass. Values are
# validated so a request can never smuggle arbitrary arguments to the CLI.
COMMANDS = {
    "profile": {},
    "tls-check": {},
    "stats": {},
    "discover": {"count": int, "batches": int, "query": str, "countries": str,
                 "verify_emails": bool, "fresh": bool},
    "verify": {"repair": bool, "apply": bool, "top": int},
    "run": {"max_professors": int, "min_score": float, "budget": float, "no_enrich": bool},
    "send": {"live": bool, "review": bool, "top": int, "limit": int,
             "local_window": str, "wait": bool, "allow_unverified": bool},
    "check-replies": {"dry_run": bool},
    "replies": {"redraft": bool, "approve_all": bool, "send": bool, "live": bool},
}
SAFE_STR = re.compile(r"^[\w\s;,.:@+\-/()&'\"]{0,300}$")


# ------------------------------------------------------------------ storage
def _hash(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 310_000)
    return salt.hex() + "$" + dk.hex()


def _check(pw: str, stored: str) -> bool:
    salt, _, _ = stored.partition("$")
    return hmac.compare_digest(_hash(pw, bytes.fromhex(salt)), stored)


def workspace(user_id: int) -> Path:
    ws = DATA / "users" / str(user_id)
    (ws / "output").mkdir(parents=True, exist_ok=True)
    (ws / "uploads").mkdir(exist_ok=True)
    (ws / "jobs").mkdir(exist_ok=True)
    return ws


def load_settings(row) -> dict:
    if not row["settings"]:
        return {}
    return json.loads(FERNET.decrypt(row["settings"]).decode())


def save_settings(user_id: int, values: dict) -> None:
    blob = FERNET.encrypt(json.dumps(values).encode())
    with engine.begin() as c:
        c.execute(update(users).where(users.c.id == user_id).values(settings=blob))


# ------------------------------------------------------------------ auth
@asynccontextmanager
async def lifespan(app):
    migrate()
    stop = threading.Event()
    scheduler = None
    if sending_enabled() and os.getenv("AGNOSTOS_SCHEDULER_ENABLED", "true").lower() == "true":
        with engine.begin() as c:
            c.execute(update(jobs).where(jobs.c.status == "running").values(status="interrupted"))
        scheduler = threading.Thread(target=scheduler_loop, args=(stop,), daemon=True)
        scheduler.start()
    try:
        yield
    finally:
        stop.set()
        if scheduler:
            scheduler.join(timeout=5)


app = FastAPI(title="Agnostos", docs_url="/api/docs", openapi_url="/api/openapi.json",
              lifespan=lifespan)


class Creds(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


def current_user(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Not signed in")
    with engine.connect() as c:
        row = c.execute(select(users).join(sessions, users.c.id == sessions.c.user_id)
                        .where(sessions.c.token == token)).mappings().first()
    if not row:
        raise HTTPException(401, "Session expired")
    return row


@app.post("/api/signup")
def signup(body: Creds):
    try:
        with engine.begin() as c:
            user_id = c.execute(insert(users).values(
                email=body.email.lower(), pw=_hash(body.password),
                created_at=datetime.now().isoformat(timespec="seconds"))
                .returning(users.c.id)).scalar_one()
            token = secrets.token_urlsafe(32)
            c.execute(insert(sessions).values(token=token, user_id=user_id, created_at=time.time()))
    except IntegrityError:
        raise HTTPException(409, "That email already has an account") from None
    workspace(user_id)
    return {"token": token}


@app.post("/api/login")
def login(body: Creds):
    with engine.begin() as c:
        row = c.execute(select(users).where(users.c.email == body.email.lower())).mappings().first()
        if not row or not _check(body.password, row["pw"]):
            raise HTTPException(401, "Wrong email or password")
        token = secrets.token_urlsafe(32)
        c.execute(insert(sessions).values(token=token, user_id=row["id"], created_at=time.time()))
    return {"token": token}


@app.post("/api/logout")
def logout(authorization: str = Header(default="")):
    with engine.begin() as c:
        c.execute(delete(sessions).where(
            sessions.c.token == authorization.removeprefix("Bearer ").strip()))
    return {"ok": True}


class Waitlist(BaseModel):
    email: EmailStr


@app.post("/api/waitlist")
def waitlist(body: Waitlist):
    with engine.begin() as c:
        from sqlalchemy.dialects import postgresql, sqlite
        dialect_insert = postgresql.insert if engine.dialect.name == "postgresql" else sqlite.insert
        c.execute(dialect_insert(waitlist_table).values(
            email=body.email.lower(), created_at=datetime.now().isoformat(timespec="seconds"))
            .on_conflict_do_nothing(index_elements=["email"]))
    return {"ok": True}


# ------------------------------------------------------------------ settings
@app.get("/api/me")
def me(user=Depends(current_user)):
    s = load_settings(user)
    ws = workspace(user["id"])
    files = {k: (ws / "uploads" / v).name for k, v in
             (("resume", s.get("_resume", "")), ("targets", s.get("_targets", "")),
              ("cv", s.get("_cv", ""))) if v and (ws / "uploads" / v).exists()}
    masked = {k: ("••••" + v[-4:] if k in SECRET_KEYS and v else v)
              for k, v in s.items() if not k.startswith("_")}
    return {"email": user["email"], "settings": masked, "files": files,
            "schedule": json.loads(user["schedule"] or "{}"),
            "sending_enabled": sending_enabled()}


@app.put("/api/settings")
def put_settings(values: dict[str, str], user=Depends(current_user)):
    s = load_settings(user)
    for k, v in values.items():
        if k not in USER_KEYS:
            raise HTTPException(400, f"Unknown setting {k}")
        if k in SECRET_KEYS and str(v).startswith("••••"):
            continue  # untouched masked value
        s[k] = str(v).strip()
    save_settings(user["id"], s)
    return {"ok": True}


@app.post("/api/upload/{kind}")
async def upload(kind: str, file: UploadFile = File(...), user=Depends(current_user)):
    allowed = {"resume": {".pdf", ".docx"}, "targets": {".xlsx"}, "cv": {".pdf"}}
    if kind not in allowed:
        raise HTTPException(400, "kind must be resume, targets or cv")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed[kind]:
        raise HTTPException(400, f"{kind} must be one of {sorted(allowed[kind])}")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Max 15 MB")
    name = f"{kind}{ext}"
    (workspace(user["id"]) / "uploads" / name).write_bytes(data)
    s = load_settings(user)
    s[f"_{kind}"] = name
    save_settings(user["id"], s)
    return {"ok": True, "file": name}


# ------------------------------------------------------------------ jobs
def _env_for(user) -> dict:
    s = load_settings(user)
    ws = workspace(user["id"])
    env = {k: v for k, v in os.environ.items()
           if k in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "LANG", "SSL_CERT_FILE",
                    "USERPROFILE", "APPDATA", "LOCALAPPDATA"}}
    env.update({k: v for k, v in s.items() if k in USER_KEYS and v})
    env["OUTPUT_DIR"] = str(ws / "output")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    targets = s.get("_targets") and ws / "uploads" / s["_targets"]
    # discover writes output/professors.xlsx; use it when nothing was uploaded.
    env["TARGET_XLSX"] = str(targets if targets and targets.exists()
                             else ws / "output" / "professors.xlsx")
    if s.get("_resume"):
        env["RESUME_PATH"] = str(ws / "uploads" / s["_resume"])
    if s.get("_cv"):
        env["ATTACHMENTS"] = str(ws / "uploads" / s["_cv"])
    return env


def _argv(command: str, opts: dict) -> list[str]:
    spec = COMMANDS.get(command)
    if spec is None:
        raise HTTPException(400, f"Unknown command {command}")
    argv = ([sys.executable, "--cli", command] if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "outreach.cli", command])
    for key, val in (opts or {}).items():
        typ = spec.get(key)
        if typ is None:
            raise HTTPException(400, f"{command} has no option {key}")
        flag = "--" + key.replace("_", "-")
        if typ is bool:
            if val is True:
                argv.append(flag)
        elif val not in (None, ""):
            try:
                cast = typ(val)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{key} must be {typ.__name__}")
            if typ is str and not SAFE_STR.match(cast):
                raise HTTPException(400, f"{key} has unsupported characters")
            argv += [flag, str(cast)]
    # Never block on a [Y/N] prompt: stdin is closed in the server.
    if command in {"run", "send"} or (command == "replies" and opts.get("send")):
        argv.append("--yes")
    return argv


def _running(user_id: int):
    with engine.connect() as c:
        return c.execute(select(jobs).where(
            jobs.c.user_id == user_id, jobs.c.status == "running")).mappings().first()


def start_job(user, command: str, opts: dict) -> int:
    if not sending_enabled() and (command == "send" or
                                  (command == "replies" and opts.get("send"))):
        raise HTTPException(403, "Sending is disabled on this deployment")
    if _running(user["id"]):
        raise HTTPException(409, "A job is already running; wait or cancel it")
    argv = _argv(command, opts)
    ws = workspace(user["id"])
    with engine.begin() as c:
        job_id = c.execute(insert(jobs).values(
            user_id=user["id"], command=command, args=json.dumps(opts), status="running",
            started_at=datetime.now().isoformat(timespec="seconds"))
            .returning(jobs.c.id)).scalar_one()
    log = open(ws / "jobs" / f"{job_id}.log", "w", encoding="utf-8")
    proc = subprocess.Popen(argv, cwd=ROOT, env=_env_for(user), stdout=log,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    with engine.begin() as c:
        c.execute(update(jobs).where(jobs.c.id == job_id).values(pid=proc.pid))

    def reap():
        code = proc.wait()
        log.close()
        with engine.begin() as c:
            c.execute(update(jobs).where(jobs.c.id == job_id, jobs.c.status == "running")
                      .values(status="done" if code == 0 else "failed", exit_code=code,
                              finished_at=datetime.now().isoformat(timespec="seconds")))
    threading.Thread(target=reap, daemon=True).start()
    return job_id


class JobReq(BaseModel):
    command: str
    options: dict = {}


@app.post("/api/jobs")
def create_job(req: JobReq, user=Depends(current_user)):
    return {"id": start_job(user, req.command, req.options)}


@app.get("/api/jobs")
def list_jobs(user=Depends(current_user)):
    with engine.connect() as c:
        rows = c.execute(select(jobs.c.id, jobs.c.command, jobs.c.args, jobs.c.status,
                                jobs.c.started_at, jobs.c.finished_at, jobs.c.exit_code)
                         .where(jobs.c.user_id == user["id"]).order_by(jobs.c.id.desc())
                         .limit(30)).mappings().all()
    return [dict(r) for r in rows]


@app.get("/api/jobs/{job_id}/log", response_class=PlainTextResponse)
def job_log(job_id: int, tail: int = 200, user=Depends(current_user)):
    path = workspace(user["id"]) / "jobs" / f"{int(job_id)}.log"
    if not path.exists():
        raise HTTPException(404, "No such job")
    text = path.read_text(encoding="utf-8", errors="replace")
    # Collapse countdown carriage-return spam into its latest frame.
    lines = [ln.split("\r")[-1] for ln in text.splitlines()]
    return "\n".join(lines[-max(1, min(tail, 2000)):])


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int, user=Depends(current_user)):
    with engine.begin() as c:
        row = c.execute(select(jobs).where(jobs.c.id == job_id, jobs.c.user_id == user["id"],
                                           jobs.c.status == "running")).mappings().first()
        if not row:
            raise HTTPException(404, "No running job with that id")
        try:
            os.kill(row["pid"], 15 if os.name != "nt" else 9)
        except OSError:
            pass
        c.execute(update(jobs).where(jobs.c.id == job_id).values(
            status="cancelled", finished_at=datetime.now().isoformat(timespec="seconds")))
    return {"ok": True}


# ------------------------------------------------------------------ data views
@app.get("/api/stats")
def stats(user=Depends(current_user)):
    from outreach.stats import collect
    path = Path(_env_for(user)["TARGET_XLSX"])
    if not path.exists():
        return {"empty": True}
    data = collect(path)
    return {k: (dict(v) if hasattr(v, "items") else v) for k, v in data.items()}


@app.get("/api/replies")
def get_replies(user=Depends(current_user)):
    path = workspace(user["id"]) / "output" / "reply_queue.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


class ReplyEdit(BaseModel):
    index: int
    body: str | None = None
    approved: bool | None = None


@app.put("/api/replies")
def edit_reply(edit: ReplyEdit, user=Depends(current_user)):
    path = workspace(user["id"]) / "output" / "reply_queue.json"
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if not 0 <= edit.index < len(items):
        raise HTTPException(404, "No such reply")
    if edit.body is not None:
        items[edit.index]["body"] = edit.body
    if edit.approved is not None:
        items[edit.index]["approved"] = edit.approved
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


@app.get("/api/download/workbook")
def download_workbook(user=Depends(current_user)):
    path = Path(_env_for(user)["TARGET_XLSX"])
    if not path.exists():
        raise HTTPException(404, "No workbook yet")
    return FileResponse(path, filename="agnostos-professors.xlsx")


# ------------------------------------------------------------------ scheduler
class Schedule(BaseModel):
    enabled: bool = False
    time: str = Field("12:30", pattern=r"^\d{2}:\d{2}$")
    limit: int = Field(40, ge=1, le=200)
    local_window: str = Field("9-17", pattern=r"^(\d{1,2}-\d{1,2}|off)$")
    check_replies: bool = True


@app.put("/api/schedule")
def put_schedule(body: Schedule, user=Depends(current_user)):
    if body.enabled and not sending_enabled():
        raise HTTPException(403, "Sending is disabled on this deployment")
    with engine.begin() as c:
        c.execute(update(users).where(users.c.id == user["id"]).values(schedule=body.model_dump_json()))
    return {"ok": True}


def scheduler_loop(stop: threading.Event) -> None:
    """Weekday daily send per user, plus a reply check right before it."""
    fired: set[tuple[int, str]] = set()
    while not stop.is_set():
        now = datetime.now()
        stamp = now.strftime("%H:%M")
        with engine.connect() as c:
            scheduled_users = c.execute(select(users).where(users.c.schedule.is_not(None))).mappings().all()
        for u in scheduled_users:
            sch = json.loads(u["schedule"] or "{}")
            key = (u["id"], now.strftime("%Y-%m-%d"))
            if not sch.get("enabled") or now.weekday() >= 5 or key in fired:
                continue
            if stamp >= sch.get("time", "12:30") and not _running(u["id"]):
                fired.add(key)
                try:
                    start_job(u, "send", {"live": True, "limit": sch.get("limit", 40),
                                          "local_window": sch.get("local_window", "9-17"),
                                          "wait": True})
                except HTTPException:
                    pass
        stop.wait(30)


@app.get("/api/health")
def health():
    return {"ok": True}


from .researchers import router as researcher_router

app.include_router(researcher_router(current_user))
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
