"""Optional Playwright flow against an isolated, no-scheduler local server."""
from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from cryptography.fernet import Fernet
from openpyxl import Workbook
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="agnostos-browser-") as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, AGNOSTOS_DATA=directory,
                   DATABASE_URL=f"sqlite:///{Path(directory).as_posix()}/browser.db",
                   AGNOSTOS_SCHEDULER_ENABLED="false", APP_SECRET=Fernet.generate_key().decode())
        with open(Path(directory) / "server.log", "w+", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1",
                 "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                base = f"http://127.0.0.1:{port}"
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Preview server exited")
                    try:
                        with urllib.request.urlopen(base + "/api/health", timeout=1) as response:
                            if response.status == 200:
                                break
                    except (urllib.error.URLError, TimeoutError):
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Preview server did not become ready")
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    page = browser.new_page()
                    errors = []
                    page.on("pageerror", lambda exc: errors.append(str(exc)))
                    # Keep this functional flow offline and independent of font/CDN uptime.
                    page.route("https://cdn.tailwindcss.com/**",
                               lambda route: route.fulfill(content_type="text/javascript",
                                                           body="window.tailwind = {};"))
                    page.route("https://fonts.googleapis.com/**", lambda route: route.abort())
                    page.goto(base + "/app.html")
                    page.add_style_tag(content=".hidden { display: none !important; }")
                    page.locator('#auth-form [name="email"]').fill("browser@example.org")
                    page.locator('#auth-form [name="password"]').fill("browser-test-password")
                    page.locator('[data-mode="signup"]').click()
                    page.get_by_role("button", name="Researchers", exact=True).click()
                    expect(page.locator("#researcher-count")).to_have_text("0 researchers")
                    page.locator("#researcher-new").click()
                    page.locator('#researcher-form [name="name"]').fill("Ada Browser")
                    page.locator('#researcher-form [name="email"]').fill("ada@example.org")
                    page.locator('#researcher-form [name="institution"]').fill("Physics Institute")
                    page.locator('#researcher-form [name="research_area"]').fill("Particle physics")
                    page.get_by_role("button", name="Save researcher", exact=True).click()
                    expect(page.locator("#researcher-rows")).to_contain_text("Ada Browser")
                    page.get_by_role("button", name="Edit", exact=True).click()
                    page.locator('#researcher-form [name="name"]').fill("Ada Updated")
                    page.get_by_role("button", name="Save researcher", exact=True).click()
                    expect(page.locator("#researcher-rows")).to_contain_text("Ada Updated")
                    page.locator('#researcher-search [name="q"]').fill("no matching record")
                    page.get_by_role("button", name="Search", exact=True).click()
                    expect(page.locator("#researcher-count")).to_have_text("0 researchers")
                    page.locator('#researcher-search [name="q"]').fill("")
                    page.get_by_role("button", name="Search", exact=True).click()
                    expect(page.locator("#researcher-count")).to_have_text("1-1 of 1")
                    book = Workbook()
                    book.active.append(["Name", "Email", "Institution"])
                    book.active.append(["Imported Scientist", "scientist@example.org", "Institute"])
                    data = BytesIO()
                    book.save(data)
                    book.close()
                    page.locator("#researcher-file").set_input_files({
                        "name": "contacts.xlsx",
                        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "buffer": data.getvalue(),
                    })
                    expect(page.locator("#researcher-message")).to_contain_text("Imported 1")
                    expect(page.locator("#researcher-count")).to_have_text("1-2 of 2")
                    with page.expect_download() as downloaded:
                        page.locator("#researcher-export").click()
                    assert downloaded.value.suggested_filename == "agnostos-researchers.xlsx"
                    page.reload()
                    page.add_style_tag(content=".hidden { display: none !important; }")
                    page.get_by_role("button", name="Researchers", exact=True).click()
                    expect(page.locator("#researcher-count")).to_have_text("1-2 of 2")
                    page.on("dialog", lambda dialog: dialog.accept())
                    page.get_by_role("button", name="Delete", exact=True).first.click()
                    expect(page.locator("#researcher-count")).to_have_text("1-1 of 1")
                    assert not errors, errors
                    browser.close()
                print("Browser flow passed: signup, create, edit, search, import, export, reload, delete.")
            except Exception:
                log.flush()
                log.seek(0)
                print(log.read())
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
