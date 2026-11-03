"""Local Windows desktop entry point for the existing FastAPI dashboard."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import sys
import threading
import time


def data_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("LOCALAPPDATA is required for the Windows desktop app")
    return Path(base) / "Agnostos"


def configure() -> Path:
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    # These must be set before server.database or server.app is imported.
    os.environ["AGNOSTOS_DATA"] = str(directory)
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("APP_SECRET", None)
    os.environ["AGNOSTOS_LIVE_SEND_ENABLED"] = "false"
    os.environ["AGNOSTOS_SCHEDULER_ENABLED"] = "false"
    return directory


def serve():
    import uvicorn
    from server.app import app

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                          log_level="warning", access_log=False,
                                          log_config=None))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                return server, thread, f"http://127.0.0.1:{port}"
            if not thread.is_alive():
                raise RuntimeError("Local server failed to start")
            time.sleep(0.05)
        raise RuntimeError("Local server did not start within 10 seconds")
    except BaseException:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        raise


def main() -> int:
    if len(sys.argv) > 1:
        if sys.argv[1] == "--cli":
            # Only the bundled job subprocess uses this path.
            arguments = sys.argv[2:]
            if not arguments or arguments[0] == "send" or "--live" in arguments or (
                arguments[0] == "replies" and "--send" in arguments
            ):
                return 1
            from outreach.cli import main as cli_main
            sys.argv = ["outreach", *arguments]
            return cli_main()
        if sys.argv[1] != "--health-check" or len(sys.argv) != 2:
            raise SystemExit("Unknown desktop argument")

    configure()
    server, thread, url = serve()
    try:
        if len(sys.argv) > 1:
            import urllib.request
            with urllib.request.urlopen(url + "/api/health", timeout=5) as response:
                if response.status != 200 or response.read() != b'{"ok":true}':
                    raise RuntimeError("Local health check failed")
            return 0
        import webview
        webview.create_window("Agnostos", url + "/app.html", width=1200, height=800,
                              min_size=(800, 600))
        webview.start(gui="edgechromium")
        return 0
    finally:
        server.should_exit = True
        thread.join(timeout=10)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        if os.name == "nt":
            import ctypes
            import traceback
            try:
                directory = data_directory()
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "startup-error.log").write_text(
                    traceback.format_exc(), encoding="utf-8")
            except OSError:
                pass
            ctypes.windll.user32.MessageBoxW(None, str(exc), "Agnostos could not start", 0x10)
        raise
