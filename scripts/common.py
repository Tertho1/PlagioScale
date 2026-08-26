"""Shared helpers for PlagioScale demo/test scripts.

Every script in scripts/ imports from here so that:
  * the API base URL is resolved in one place (nginx proxy on :3050 —
    api-service has no published host port),
  * login/signup handles JWT + httpOnly cookies + CSRF tokens,
  * docker queries are compose-project aware (label filters),
  * interactive pauses can be skipped with --yes or NONINTERACTIVE=1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import requests

# Windows consoles default to cp1252; force UTF-8 so box-drawing/check marks
# in script output never raise UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Configuration ────────────────────────────────────────────────────────────

API = os.getenv("PLAGIOSCALE_API", "http://localhost:3050/api")
FRONTEND = os.getenv("PLAGIOSCALE_FRONTEND", "http://localhost:3050")
MONITORING = os.getenv("PLAGIOSCALE_MONITORING", "http://localhost:8090")
AUTOSCALER_METRICS = os.getenv("PLAGIOSCALE_AUTOSCALER", "http://localhost:8002/metrics")

DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@plagioscale.dev")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "Admin123!")
DEMO_NAME = os.getenv("DEMO_NAME", "Demo Admin")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "plagio_redis_pass")

# NONINTERACTIVE=1 env or --yes argv flag skips all input() pauses.
NON_INTERACTIVE = os.getenv("NONINTERACTIVE", "").lower() in ("1", "true", "yes") or "--yes" in sys.argv


def pause(msg: str = "\nPress Enter to continue...") -> None:
    if NON_INTERACTIVE:
        return
    try:
        input(msg)
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(1)


def run(cmd, timeout: int = 30) -> str:
    """Run a command list (shell=False) and return stripped stdout."""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       errors="replace")
    return (r.stdout or "").strip()


# ── Docker helpers (compose-project aware via labels) ────────────────────────

def detect_project() -> str:
    """Best-effort compose project name from running containers."""
    env_project = os.getenv("COMPOSE_PROJECT_NAME")
    if env_project:
        return env_project
    raw = run(["docker", "ps", "--filter",
               "label=com.docker.compose.service=api-service",
               "--format", "{{.Label \"com.docker.compose.project\"}}"])
    project = raw.splitlines()[0].strip() if raw else ""
    return project or "plagioscale"


PROJECT = detect_project()


def service_containers(service: str) -> list[dict]:
    """Running containers of a compose service: [{name, status, ip}]."""
    raw = run([
        "docker", "ps",
        "--filter", f"label=com.docker.compose.service={service}",
        "--filter", f"label=com.docker.compose.project={PROJECT}",
        "--format", "{{.Names}}~{{.Status}}~{{.ID}}",
    ])
    out = []
    for line in raw.splitlines():
        parts = line.split("~")
        if len(parts) < 3:
            continue
        name, status, cid = parts[0], parts[1], parts[2]
        ip_raw = run(["docker", "inspect", name, "--format",
                      "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}"])
        ips = ip_raw.split()
        out.append({"name": name, "status": status, "ip": ips[0] if ips else "", "id": cid})
    return out


def short(name: str) -> str:
    return name.replace(f"{PROJECT}-", "")


def worker_container() -> str | None:
    workers = service_containers("worker")
    return workers[0]["name"] if workers else None


# ── Redis ─────────────────────────────────────────────────────────────────────

def redis_client():
    import redis
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                       password=REDIS_PASSWORD, socket_connect_timeout=3)


# ── Auth-aware API client ────────────────────────────────────────────────────

class PlagioClient(requests.Session):
    """requests.Session that logs in and attaches CSRF tokens automatically.

    The API requires, for state-changing endpoints:
      * a valid JWT (Authorization header or httpOnly cookie), AND
      * X-CSRF-Token header == csrf_token cookie == HMAC(CSRF_SECRET, user_id).
    Login sets both cookies; we fetch the token once and mirror it into the
    header on every POST/PUT/DELETE/PATCH.
    """

    STATE_CHANGING = {"POST", "PUT", "DELETE", "PATCH"}

    def __init__(self):
        super().__init__()
        self.token: str | None = None
        self.user: dict | None = None

    # -- auth ---------------------------------------------------------------
    def login_or_signup(self, email: str = DEMO_EMAIL, password: str = DEMO_PASSWORD,
                        name: str = DEMO_NAME) -> bool:
        r = self.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=10)
        if r.status_code != 200:
            r = self.post(f"{API}/auth/signup",
                          json={"email": email, "password": password, "name": name},
                          timeout=10)
            if r.status_code != 200:
                print(f"  Auth failed: signup {r.status_code}: {r.text[:120]}")
                return False
        # (Re-)login to get a clean token + cookies
        r = self.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=10)
        if r.status_code != 200:
            print(f"  Auth failed: login {r.status_code}: {r.text[:120]}")
            return False
        self.token = r.json().get("access_token")
        # Fetch CSRF token (endpoint requires JWT; also (re)sets the cookie)
        r = self.get(f"{API}/auth/csrf-token", timeout=10)
        if r.status_code != 200:
            print(f"  CSRF fetch failed: {r.status_code}")
            return False
        self.headers.update({"Authorization": f"Bearer {self.token}"})
        me = self.get(f"{API}/auth/me", timeout=10)
        self.user = me.json() if me.status_code == 200 else None
        return True

    def refresh_csrf(self) -> bool:
        r = self.get(f"{API}/auth/csrf-token", timeout=10)
        return r.status_code == 200

    # -- request hook ---------------------------------------------------------
    def request(self, method, url, **kw):  # noqa: D102
        if method.upper() in self.STATE_CHANGING:
            csrf = self.cookies.get("csrf_token")
            if csrf:
                headers = kw.pop("headers", {}) or {}
                headers.setdefault("X-CSRF-Token", csrf)
                kw["headers"] = headers
        return super().request(method, url, **kw)


def autoscaler_events(limit: int = 5, level_filter: str | None = None,
                      message_prefixes: tuple | None = None) -> list[dict]:
    """Recent autoscaler events via the monitoring service (proves decisions).

    Filters first (the raw feed is flooded with 5s debug ticks), so callers
    get `limit` MATCHING events, not `limit` raw ones.
    """
    try:
        r = requests.get(f"{MONITORING}/api/events?limit=100", timeout=5)
        events = r.json().get("events", [])
    except Exception:
        return []
    if level_filter:
        events = [e for e in events if e.get("level") == level_filter]
    if message_prefixes:
        events = [e for e in events
                  if str(e.get("message", "")).lower().startswith(message_prefixes)]
    return events[:limit]


def container_http_json(container: str, url: str, timeout_s: int = 4):
    """Fetch a JSON URL from INSIDE the compose network by relaying through
    `docker exec` (container IPs are not routable from the Windows host).

    Returns parsed JSON or None."""
    py = ("import json,urllib.request;print(json.dumps(json.load("
          f"urllib.request.urlopen({url!r}, timeout={timeout_s}))))")
    raw = run(["docker", "exec", container, "python", "-c", py], timeout=timeout_s + 6)
    if not raw:
        return None
    try:
        line = raw.strip().splitlines()[-1]
        return json.loads(line)
    except Exception:
        return None


def print_events(events: list[dict], indent: str = "    ") -> None:
    for e in events:
        ts = str(e.get("timestamp", ""))[11:19]
        extra = {k: v for k, v in e.items()
                 if k not in ("timestamp", "level", "message")}
        suffix = f" ({json.dumps(extra)})" if extra else ""
        print(f"{indent}[{ts}] {e.get('message', '')}{suffix}")
