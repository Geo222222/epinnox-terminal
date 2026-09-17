from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = int(os.getenv("EPINNOX_SMOKE_PORT", "8765"))
BASE = f"http://{HOST}:{PORT}"
TIMEOUT_SECONDS = 30


def fetch(path: str) -> tuple[int, str, str]:
    request = urllib.request.Request(f"{BASE}{path}", headers={"Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=5) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.status, response.headers.get("content-type", ""), body


def wait_until_ready(process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"uvicorn exited before becoming ready with code {process.returncode}")
        try:
            status, _, body = fetch("/api/health")
            if status == 200:
                payload = json.loads(body)
                if payload.get("ok") is True and payload.get("service") == "epinnox-terminal":
                    return
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"runtime did not become ready within {TIMEOUT_SECONDS}s: {last_error}")


def assert_contains(path: str, marker: str) -> None:
    status, _, body = fetch(path)
    if status != 200:
        raise AssertionError(f"{path} returned {status}, expected 200")
    if marker not in body:
        raise AssertionError(f"{path} is missing runtime marker {marker!r}")
    print(f"[ok] {path} -> 200 and contains {marker!r}")


def assert_not_contains(path: str, marker: str) -> None:
    status, _, body = fetch(path)
    if status != 200:
        raise AssertionError(f"{path} returned {status}, expected 200")
    if marker in body:
        raise AssertionError(f"{path} unexpectedly contains obsolete marker {marker!r}")
    print(f"[ok] {path} -> does not contain obsolete marker {marker!r}")


def assert_json_contract(path: str, checks: dict[str, object]) -> None:
    status, content_type, body = fetch(path)
    if status != 200:
        raise AssertionError(f"{path} returned {status}, expected 200")
    if "application/json" not in content_type:
        raise AssertionError(f"{path} returned unexpected content-type {content_type!r}")
    payload = json.loads(body)
    for dotted_key, expected in checks.items():
        value: object = payload
        for part in dotted_key.split("."):
            if not isinstance(value, dict) or part not in value:
                raise AssertionError(f"{path} is missing JSON field {dotted_key!r}")
            value = value[part]
        if value != expected:
            raise AssertionError(f"{path} field {dotted_key!r} = {value!r}, expected {expected!r}")
    print(f"[ok] {path} -> JSON contract verified")


def run() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    # The smoke gate validates contracts, not external HTX reachability. Keeping
    # live ingestion disabled prevents a CI network condition from masquerading
    # as an application-runtime failure.
    env["EPINNOX_DISABLE_LIVE_INTELLIGENCE"] = "1"
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--log-level",
        "warning",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        wait_until_ready(process)
        print(f"[ok] Epinnox Terminal runtime ready at {BASE}")

        assert_json_contract(
            "/api/health",
            {"ok": True, "service": "epinnox-terminal"},
        )
        assert_json_contract(
            "/api/config",
            {
                "execution.account_context": "epinnox-online-session",
                "execution.live_order_routing_armed": False,
                "execution.multi_session": True,
            },
        )
        assert_json_contract(
            "/api/live/status",
            {
                "schema_version": 2,
                "started": False,
                "controls.universe_enabled": True,
                "controls.scanner_enabled": True,
            },
        )
        assert_json_contract(
            "/api/live/universe",
            {"schema_version": 2},
        )

        for path, marker in {
            "/": 'id="sessionRail"',
            "/scanner": "CANDIDATE LEADERBOARD",
            "/sessions": "SESSION REGISTRY",
            "/research": "UNIVERSE CANDIDATES",
            "/strategies": "MODEL CATALOG",
        }.items():
            assert_contains(path, marker)

        # The canonical home surface must be fully declared at first paint.
        for marker in (
            '/static/v4-workbench.css',
            '/static/v4-universe.css',
            '/static/v5-chart-workspace.css',
            '/static/v4-workbench.js',
            '/static/v4-universe.js',
            '/static/v5-chart-workspace.js',
        ):
            assert_contains("/", marker)

        for path, marker in {
            "/static/v4-shell.js": "Canonical home-page assets are loaded directly by index.html",
            "/static/v4-universe.js": "LIVE UNIVERSE",
            "/static/v4-universe.css": "prefers-reduced-motion",
            "/static/v5-chart-workspace.css": "min-height:180px!important",
            "/static/product-visual-qa.css": "prefers-reduced-motion",
            "/static/research.js": "epinnox.universe.saved.v1",
        }.items():
            assert_contains(path, marker)

        for obsolete in (
            "v4-command-center",
            "v4-scanner-v2",
            "v4-final-chrome",
            "v4-sitewide",
            "v4-visual-qa",
        ):
            assert_not_contains("/static/v4-shell.js", obsolete)
            assert_not_contains("/", obsolete)

        assert_json_contract("/api/scanner/runs?limit=1", {"schema_version": 1})
        print("[ok] runtime smoke gate passed without market-data or execution mutations")
    except Exception:
        print("\n[runtime-smoke] FAILED", file=sys.stderr)
        raise
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdout is not None:
            logs = process.stdout.read().strip()
            if logs:
                print("\n--- uvicorn output ---")
                print(logs)


if __name__ == "__main__":
    run()
