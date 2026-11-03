"""Desktop startup and existing dashboard flow against project-local test data."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import unittest
import urllib.request
from urllib.parse import urlsplit
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import desktop


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.local = ROOT / "build" / "desktop-test-data"
        if cls.local.exists():
            shutil.rmtree(cls.local)
        cls.local.mkdir(parents=True)
        cls.environment = patch.dict(os.environ, {
            "LOCALAPPDATA": str(cls.local),
            "PLAYWRIGHT_BROWSERS_PATH": str(
                Path.home() / "AppData" / "Local" / "ms-playwright"),
            "DATABASE_URL": "postgresql://not-a-real-server/invalid",
            "AGNOSTOS_LIVE_SEND_ENABLED": "true",
            "AGNOSTOS_SCHEDULER_ENABLED": "true",
        })
        cls.environment.start()
        desktop.configure()
        cls.server, cls.thread, cls.url = desktop.serve()

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=10)
        from server.database import engine
        engine.dispose()
        cls.environment.stop()
        shutil.rmtree(cls.local)

    def request(self, path, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(
            self.url + path, data=json.dumps(body).encode() if body is not None else None,
            headers=headers)
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()

    def test_dashboard_and_database(self):
        from server.database import DATA, ROOT as assets
        self.assertEqual(DATA, self.local / "Agnostos")
        self.assertEqual(assets, ROOT)
        self.assertTrue((DATA / "agnostos.db").exists())
        self.assertTrue((DATA / ".app_secret").exists())
        self.assertEqual(self.request("/api/health"), (200, b'{"ok":true}'))
        self.assertIn(b"researchers.js", self.request("/app.html")[1])
        self.assertIn(b"/site.css", self.request("/app.html")[1])
        self.assertIn(b"/site.css", self.request("/")[1])
        self.assertEqual(self.request("/fonts/outfit-latin-400-normal.woff2")[0], 200)
        self.assertEqual(self.request("/fonts/reenie-beanie-latin-400-normal.woff2")[0], 200)
        self.assertIn(b"/api/${mode}", self.request("/app.js")[1])
        status, payload = self.request("/api/signup", {
            "email": "desktop@example.org", "password": "desktop-password"})
        self.assertEqual(status, 200)
        token = json.loads(payload)["token"]
        self.assertFalse(json.loads(self.request("/api/me", token=token)[1])["sending_enabled"])
        self.assertEqual(self.request("/api/researchers", token=token)[0], 200)
        self.assertTrue((DATA / "users" / "1").is_dir())

    def test_frozen_job_entry(self):
        from server.app import _argv
        with patch.object(sys, "frozen", True, create=True):
            self.assertEqual(_argv("stats", {}), [sys.executable, "--cli", "stats"])
        for arguments in (["send", "--live"], ["send"], ["replies", "--send", "--live"]):
            with self.subTest(arguments=arguments), patch.object(
                sys, "argv", ["desktop", "--cli", *arguments]
            ):
                self.assertEqual(desktop.main(), 1)

    def test_browser_flow(self):
        from playwright.sync_api import expect, sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                external = []
                def offline(route):
                    if urlsplit(route.request.url).hostname == "127.0.0.1":
                        route.continue_()
                    else:
                        external.append(route.request.url)
                        route.abort()

                page.route("**/*", offline)
                page.goto(self.url + "/")
                self.assertEqual(page.locator("body").evaluate(
                    "(element) => getComputedStyle(element).backgroundColor"), "rgb(253, 252, 248)")
                page.goto(self.url + "/app.html")
                page.evaluate("document.fonts.ready")
                self.assertEqual(page.locator("body").evaluate(
                    "(element) => getComputedStyle(element).backgroundColor"), "rgb(253, 252, 248)")
                self.assertTrue(page.evaluate("document.fonts.check('400 16px Outfit')"))
                self.assertTrue(page.evaluate("document.fonts.check('400 20px \"Reenie Beanie\"')"))
                page.goto(self.url + "/app.html")
                page.add_style_tag(content=".hidden { display: none !important; }")
                page.locator('#auth-form [name="email"]').fill("browser-desktop@example.org")
                page.locator('#auth-form [name="password"]').fill("desktop-password")
                page.locator('[data-mode="signup"]').click()
                expect(page.locator("#sending-disabled")).to_be_visible()
                page.get_by_role("button", name="Pipeline", exact=True).click()
                expect(page.get_by_role("button", name="Run").last).to_be_disabled()
                page.get_by_role("button", name="Researchers", exact=True).click()
                page.locator("#researcher-new").click()
                page.locator('#researcher-form [name="name"]').fill("Desktop Researcher")
                page.get_by_role("button", name="Save researcher", exact=True).click()
                expect(page.locator("#researcher-rows")).to_contain_text("Desktop Researcher")
                self.assertEqual(external, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
