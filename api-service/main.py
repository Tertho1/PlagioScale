"""PlagioScale API service."""

import asyncio
import csv
import io
import json
import logging
import os
import re
import shutil
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import Counter, Gauge, make_asgi_app
from pydantic import BaseModel, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

# Add shared to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from functools import partial
from typing import Optional as _Optional

import redis.asyncio as aioredis

from jose import JWTError, jwt
import bcrypt as _bcrypt

from shared.database import (
    create_assignment as db_create_assignment,
)
from shared.database import (
    create_job_record,
    create_notification,
    create_submission,
    create_user,
    get_active_submission_by_batch_and_roll,
    get_admin_stats,
    get_paginated_users,
    get_assignment,
    get_assignment_by_access_code,
    get_cross_batch_comparisons,
    get_job_record,
    get_pending_notifications,
    get_similarity_matrix,
    get_student_comparison_details,
    get_submissions_by_batch,
    get_submissions_count_by_batch,
    get_submission_by_id,
    get_user_by_email,
    get_user_by_id,
    init_db,
    list_assignments,
    mark_notification_sent,
    update_job_status,
    update_submission_status,
    update_user_role,
)
from shared.models import Job, JobStatus
from shared.queue_client import AsyncQueueClient
from shared.text_extraction import extract_text
from shared.vectorizer import TextVectorizer
from shared.audit_log import audit
from shared.email_notifier import send_email, notify_completion
from shared.external_lookup import search_external_sources
from shared.pdf_report import generate_similarity_report_pdf

# Websocket connections per batch (kept in-memory for active sockets)
ws_connections: dict[str, set[WebSocket]] = {}
_ws_rate: dict[str, list[float]] = {}
_WS_RATE_LIMIT = 10
_WS_RATE_WINDOW = 60
_WS_PUBSUB_CHANNEL = "ws:progress"
_ws_redis: _Optional[aioredis.Redis] = None


def _get_redis_config():
    return {
        "host": os.getenv("REDIS_HOST", "redis"),
        "port": int(os.getenv("REDIS_PORT", 6379)),
        "password": os.getenv("REDIS_PASSWORD", None) or None,
    }


async def _ws_pubsub_init():
    global _ws_redis
    cfg = _get_redis_config()
    _ws_redis = aioredis.Redis(**cfg, decode_responses=True)


async def _ws_pubsub_listener():
    await asyncio.sleep(2)
    if _ws_redis is None:
        await _ws_pubsub_init()
    pubsub = _ws_redis.pubsub()
    await pubsub.subscribe(_WS_PUBSUB_CHANNEL)
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            batch_id = data.get("batch_id")
            payload = data.get("payload")
            if batch_id in ws_connections and payload is not None:
                dead = []
                for ws in list(ws_connections[batch_id]):
                    try:
                        await ws.send_text(json.dumps(payload))
                    except Exception:
                        dead.append(ws)
                for d in dead:
                    ws_connections[batch_id].discard(d)
        except Exception:
            continue


def _check_ws_rate(ip: str) -> bool:
    now = time.time()
    if ip not in _ws_rate:
        _ws_rate[ip] = []
    _ws_rate[ip] = [t for t in _ws_rate[ip] if now - t < _WS_RATE_WINDOW]
    if len(_ws_rate[ip]) >= _WS_RATE_LIMIT:
        return False
    _ws_rate[ip].append(now)
    return True

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(title="PlagioScale API", version="1.0.0")


async def run_db(func, *args, **kwargs):
    """Run a synchronous DB function in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


async def _cleanup_old_data():
    """Periodically clean up old CANCELLED submissions and their files."""
    while True:
        await asyncio.sleep(3600)
        if not db_ready:
            continue
        try:
            from shared.database import Submission, SessionLocal
            from sqlalchemy import text
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            session = SessionLocal()
            try:
                old = session.query(Submission).filter(
                    Submission.status == "CANCELLED",
                    Submission.created_at < cutoff,
                ).all()
                for sub in old:
                    fp = sub.file_path
                    if fp and os.path.exists(fp):
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
                    session.delete(sub)
                if old:
                    session.commit()
                    logging.info("Cleaned up %d old cancelled submissions", len(old))
            finally:
                session.close()
        except Exception as exc:
            logging.warning("Data cleanup failed: %s", exc)


async def _cleanup_stale_ws():
    """Periodically remove dead WebSocket connections."""
    while True:
        await asyncio.sleep(30)
        for batch_id in list(ws_connections):
            dead = set()
            for ws in list(ws_connections.get(batch_id, set())):
                try:
                    await ws.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    dead.add(ws)
            for ws in dead:
                try:
                    await ws.close()
                except Exception:
                    pass
                ws_connections[batch_id].discard(ws)
            if not ws_connections.get(batch_id):
                del ws_connections[batch_id]


async def _monitor_db():
    global db_ready
    DB_READY_GAUGE.set(1 if db_ready else 0)
    while True:
        await asyncio.sleep(30)
        loop = asyncio.get_event_loop()
        try:
            from sqlalchemy import text
            from shared.database import SessionLocal
            session = SessionLocal()
            session.execute(text("SELECT 1"))
            session.close()
            if not db_ready:
                ok = await loop.run_in_executor(None, init_db)
                if ok:
                    db_ready = True
                    DB_READY_GAUGE.set(1)
                    AUTO_RECOVERY_TOTAL.labels("db_reconnect").inc()
                    logging.info("Database connection re-established")
        except Exception:
            if db_ready:
                db_ready = False
                DB_READY_GAUGE.set(0)
                logging.warning("Database connection lost — will retry")



@app.on_event("startup")
async def _start_background_tasks():
    await _ws_pubsub_init()
    asyncio.create_task(_ws_pubsub_listener())
    asyncio.create_task(_cleanup_stale_ws())
    asyncio.create_task(_cleanup_old_data())
    asyncio.create_task(_monitor_db())
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

# Allow the frontend dev container / static site to call the API from a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3050",
        "http://127.0.0.1:3050",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
REQUESTS_SUBMITTED = Counter(
    "plagioscale_requests_submitted_total", "Total submitted jobs"
)
QUEUE_LENGTH_GAUGE = Gauge("plagioscale_queue_length", "Current Redis queue length")
AUDIT_EVENTS_TOTAL = Counter(
    "plagioscale_audit_events_total", "Total audit events by action",
    ["action"]
)
DB_READY_GAUGE = Gauge("plagioscale_db_ready", "Database connection status (1=ok, 0=fail)")
AUTO_RECOVERY_TOTAL = Counter(
    "plagioscale_auto_recovery_total", "Automated recovery actions by type",
    ["type"]
)

# Mount Prometheus ASGI app at /metrics
app.mount("/metrics", make_asgi_app())
queue_client = AsyncQueueClient()
db_ready = init_db()


@app.on_event("startup")
async def _connect_redis():
    await queue_client.connect()


class SubmitRequest(BaseModel):
    """Request to submit text for plagiarism detection."""

    text: str


class ResultResponse(BaseModel):
    """Response with job result."""

    job_id: str
    status: str
    result: dict = None
    error: str = None


class SignupRequest(BaseModel):
    email: EmailStr
    name: str | None = None
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Auth helpers (module-level)
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable must be set")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
WORKER_SECRET = os.getenv("WORKER_SECRET", "")
CSRF_SECRET = os.getenv("CSRF_SECRET", JWT_SECRET)

COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", None)


def hash_password(password: str) -> str:
    try:
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()
    except Exception as e:
        logging.error(f"Password hashing failed: {e}")
        raise HTTPException(status_code=500, detail="Internal error")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_access_token(subject: str, token_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    data = {"sub": subject, "exp": expire, "ver": token_version}
    token = jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def generate_csrf_token() -> str:
    return str(uuid.uuid4())


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=JWT_EXPIRE_MINUTES * 60,
        domain=COOKIE_DOMAIN,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.set_cookie(
        key="access_token",
        value="",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=0,
        domain=COOKIE_DOMAIN,
        path="/",
    )


def set_csrf_cookie(response: Response, csrf: str) -> None:
    response.set_cookie(
        key="csrf_token",
        value=csrf,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=JWT_EXPIRE_MINUTES * 60,
        domain=COOKIE_DOMAIN,
        path="/",
    )


def decode_access_token(token: str) -> _Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def get_current_user(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
    token_param: str | None = Query(default=None, alias="token"),
) -> dict:
    """Resolve the current user from a Bearer JWT or httpOnly cookie."""
    token = None
    if authorization:
        prefix = "Bearer "
        if authorization.startswith(prefix):
            token = authorization[len(prefix):].strip()
    if not token:
        token = access_token
    if not token:
        token = token_param
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization")

    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = get_user_by_id(user_id) if db_ready else {"user_id": user_id}
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Check token version for session invalidation on role change
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        token_ver = payload.get("ver", 0)
        db_ver = user.get("token_version", 0)
        if token_ver != db_ver:
            raise HTTPException(status_code=401, detail="Session expired — please log in again")
    except HTTPException:
        raise
    except Exception:
        pass

    user["role"] = user.get("role", "user")
    return user


def require_csrf(x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"), csrf_token: str | None = Cookie(default=None)) -> None:
    """Validate CSRF token for state-changing requests (applies to cookie-auth only)."""
    if not x_csrf_token or not csrf_token:
        raise HTTPException(status_code=403, detail="CSRF token required")
    if x_csrf_token != csrf_token:
        raise HTTPException(status_code=403, detail="CSRF token mismatch")


def require_role(required_role: str):
    """Dependency factory: require a specific role to access an endpoint."""
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") != required_role and required_role != "user":
            raise HTTPException(status_code=403, detail=f"{required_role} role required")
        return current_user
    return role_checker
    """Verify that the request comes from an authorized worker."""
    if not WORKER_SECRET:
        return False
    return x_worker_secret == WORKER_SECRET


def get_optional_user(authorization: str | None = Header(default=None)) -> dict | None:
    """Resolve current user from JWT if present, return None otherwise."""
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    token = authorization[len(prefix):].strip()
    user_id = decode_access_token(token)
    if not user_id:
        return None
    user = get_user_by_id(user_id) if db_ready else {"user_id": user_id}
    return user





@app.get("/health")
async def health_check():
    """Health check endpoint with dependency status."""
    deps = {"redis": False, "database": db_ready}
    try:
        r = aioredis.Redis(**_get_redis_config(), decode_responses=True)
        await r.ping()
        await r.aclose()
        deps["redis"] = True
    except Exception:
        pass
    all_ok = deps["redis"] and deps["database"]
    status = "healthy" if all_ok else "degraded"
    return {"status": status, "service": "api-service", "dependencies": deps}


@app.post("/submit")
@limiter.limit("100/minute")
async def submit_text(request: Request, body: SubmitRequest):
    """
    Submit text for plagiarism detection.

    Returns job_id for later result retrieval.
    """
    if not body.text or len(body.text.strip()) < 10:
        raise HTTPException(
            status_code=400, detail="Text must be at least 10 characters"
        )

    job_id = str(uuid.uuid4())
    job = Job(job_id=job_id, text=body.text)

    if await queue_client.enqueue_job(job):
        if db_ready:
            create_job_record(
                job_id=job_id, text=body.text, status=JobStatus.PENDING.value
            )
        REQUESTS_SUBMITTED.inc()
        return {
            "job_id": job_id,
            "status": "submitted",
            "message": "Job queued for processing",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to queue job")


@app.get("/result/{job_id}")
async def get_result(job_id: str):
    """
    Retrieve plagiarism detection result.
    """
    if db_ready:
        db_record = get_job_record(job_id)
        if db_record:
            return {
                "job_id": db_record["job_id"],
                "status": db_record["status"],
                "result": db_record["result"],
                "error": db_record["error"],
            }

    status = await queue_client.get_job_status(job_id)

    if not status:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await queue_client.get_result(job_id)

    return {"job_id": job_id, "status": status, "result": result}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Get job processing status."""
    if db_ready:
        db_record = get_job_record(job_id)
        if db_record:
            return {
                "job_id": db_record["job_id"],
                "status": db_record["status"],
                "error": db_record.get("error"),
            }

    status = await queue_client.get_job_status(job_id)

    if not status:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"job_id": job_id, "status": status, "error": None}


@app.get("/queue/stats")
async def queue_stats():
    """Get queue statistics."""
    queue_length = await queue_client.get_queue_length()
    try:
        QUEUE_LENGTH_GAUGE.set(queue_length)
    except Exception:
        logging.warning("Failed to update queue length gauge")
    return {"queue_length": queue_length, "message": f"{queue_length} jobs waiting"}


@app.post("/auth/signup", response_model=TokenResponse)
@limiter.limit("10/minute")
async def auth_signup(request: Request, body: SignupRequest):
    """Create a new user account and return an access token."""
    existing = get_user_by_email(body.email) if db_ready else None
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid.uuid4())
    pwd_hash = hash_password(body.password)
    created = False
    if db_ready:
        try:
            created = create_user(user_id=user_id, email=body.email, name=body.name, password_hash=pwd_hash)
        except Exception:
            created = False

    if not created:
        raise HTTPException(status_code=500, detail="Failed to create user")

    token = create_access_token(user_id, token_version=0)
    csrf = generate_csrf_token()
    response = JSONResponse({"access_token": token, "token_type": "bearer"})
    set_auth_cookie(response, token)
    set_csrf_cookie(response, csrf)
    audit("auth.signup", actor=user_id, detail={"email": body.email})
    return response


@app.post("/auth/login", response_model=TokenResponse)
@limiter.limit("20/minute")
async def auth_login(request: Request, body: LoginRequest):
    """Authenticate user and return access token."""
    user = get_user_by_email(body.email) if db_ready else None
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    pwd_hash = user.get("password_hash")
    if not verify_password(body.password, pwd_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user.get("user_id"), token_version=user.get("token_version", 0))
    csrf = generate_csrf_token()
    response = JSONResponse({"access_token": token, "token_type": "bearer"})
    set_auth_cookie(response, token)
    set_csrf_cookie(response, csrf)
    audit("auth.login", actor=user.get("user_id"), detail={"email": body.email})
    return response


@app.post("/auth/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def auth_refresh(request: Request, current_user: dict = Depends(get_current_user)):
    """Issue a new access token from a valid existing one."""
    db_user = get_user_by_id(current_user.get("user_id"))
    token_version = db_user.get("token_version", 0) if db_user else 0
    token = create_access_token(current_user.get("user_id"), token_version=token_version)
    csrf = generate_csrf_token()
    response = JSONResponse({"access_token": token, "token_type": "bearer"})
    set_auth_cookie(response, token)
    set_csrf_cookie(response, csrf)
    return response


@app.post("/auth/logout")
async def auth_logout(response: Response):
    """Clear auth and CSRF cookies."""
    clear_auth_cookie(response)
    response.set_cookie(key="csrf_token", value="", httponly=False, max_age=0, path="/")
    return {"ok": True}


@app.get("/auth/csrf-token")
async def get_csrf_token(response: Response):
    """Return (and set) a fresh CSRF token cookie."""
    csrf = generate_csrf_token()
    set_csrf_cookie(response, csrf)
    return {"csrf_token": csrf}


@app.get("/auth/me")
async def auth_me(current_user: dict = Depends(get_current_user)):
    """Return current user info (used by frontend to check auth state)."""
    return {
        "user_id": current_user.get("user_id"),
        "email": current_user.get("email"),
        "name": current_user.get("name"),
        "role": current_user.get("role"),
    }




@app.post("/portal/assignments")
async def create_assignment(body: dict, current_user: dict = Depends(get_current_user)):
    """Create a new assignment/batch and return batch_id and access_code."""
    name = body.get("name") or body.get("assignment") or "Assignment"
    expected = int(body.get("expected_count", 0) or 0)
    similarity_threshold = float(body.get("similarity_threshold", 0.5))
    due_date = body.get("due_date")
    if due_date:
        due_date = datetime.fromisoformat(due_date)
    allowed_file_types = body.get("allowed_file_types", ".pdf,.docx,.txt")
    allow_anonymous = bool(body.get("allow_anonymous", True))
    batch_id = str(uuid.uuid4())
    access_code = uuid.uuid4().hex[:8]
    ws_connections[batch_id] = set()
    if db_ready:
        ok = await run_db(
            db_create_assignment,
            batch_id=batch_id,
            name=name,
            access_code=access_code,
            expected_count=expected,
            owner_user_id=current_user.get("user_id"),
            similarity_threshold=similarity_threshold,
            due_date=due_date,
            allowed_file_types=allowed_file_types,
            allow_anonymous=allow_anonymous,
        )
        if not ok:
            raise HTTPException(
                status_code=500,
                detail="Failed to create assignment — database write failed",
            )
    audit("assignment.create", actor=current_user.get("user_id"), resource=batch_id, detail={"name": name})
    return {"batch_id": batch_id, "access_code": access_code}


@app.get("/portal/assignments")
async def list_portal_assignments(current_user: dict = Depends(get_current_user)):
    """List assignments for the dashboard."""
    assignments = await run_db(list_assignments) if db_ready else []
    owned = []
    other = []
    for assignment in assignments:
        if assignment.get("owner_user_id") == current_user.get("user_id"):
            owned.append(assignment)
        else:
            other.append(assignment)
    return {
        "owned": owned,
        "shared": other,
        "all": assignments,
    }


@app.get("/portal/assignments/{batch_id}")
async def get_portal_assignment(batch_id: str, current_user: dict = Depends(get_current_user)):
    """Return details for a single assignment, including submissions and matrix presence."""
    assignment = await run_db(get_assignment, batch_id) if db_ready else None
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    submissions = await run_db(get_submissions_by_batch, batch_id) if db_ready else []
    matrix = await run_db(get_similarity_matrix, batch_id) if db_ready else {}
    return {
        "assignment": assignment,
        "submissions": submissions,
        "similarity_matrix_ready": bool(matrix),
        "submissions_count": len(submissions),
    }


async def broadcast_progress(batch_id: str):
    """Send progress updates to all connected websockets for a batch."""
    # fetch authoritative values from DB
    total = 0
    processed = 0
    try:
        assignment = get_assignment(batch_id) if db_ready else None
        if assignment:
            total = int(assignment.get("expected_count", 0) or 0)
    except Exception:
        logging.warning("Failed to get expected count for batch %s", batch_id)
        total = 0
    try:
        subs = get_submissions_by_batch(batch_id) if db_ready else []
        processed = len(subs)
    except Exception:
        logging.warning("Failed to get submissions for batch %s", batch_id)
        processed = 0
    payload = {"processed": processed, "total": total}
    # Publish to Redis so all replicas receive the update
    if _ws_redis is not None:
        try:
            msg = json.dumps({"batch_id": batch_id, "payload": payload})
            await _ws_redis.publish(_WS_PUBSUB_CHANNEL, msg)
        except Exception:
            pass
    # Send to local connections
    dead = []
    for ws in list(ws_connections.get(batch_id, [])):
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for d in dead:
        ws_connections[batch_id].discard(d)


@app.post("/portal/notify")
async def portal_notify(request: Request):
    """Internal endpoint used by workers to notify progress updates for a batch.

    Expects JSON: { "batch_id": "...", "processed": 10, "total": 50 }
    Requires X-Worker-Secret header matching configured WORKER_SECRET.
    """
    if WORKER_SECRET:
        worker_secret = request.headers.get("X-Worker-Secret", "")
        if worker_secret != WORKER_SECRET:
            raise HTTPException(status_code=403, detail="Forbidden")
    try:
        payload = await request.json()
        batch_id = payload.get("batch_id")
        # sanity
        if not batch_id:
            raise HTTPException(status_code=400, detail="batch_id required")
        # use DB to sanity-check counts if needed
        # broadcast to connected sockets
        await broadcast_progress(batch_id)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logging.error("portal_notify error: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".py", ".java", ".js", ".ts"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

FILE_MAGIC_BYTES = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",
    ".txt": None,
    ".md": None,
    ".csv": None,
    ".py": None,
    ".java": None,
    ".js": None,
    ".ts": None,
}


def _sanitize_filename(filename: str) -> str:
    return re.sub(r"[^\w\-_.]", "_", filename)


def _validate_file(filename: str, content: bytes) -> None:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' is not allowed")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {MAX_FILE_SIZE // (1024 * 1024)} MB)",
        )
    expected_magic = FILE_MAGIC_BYTES.get(ext)
    if expected_magic and not content.startswith(expected_magic):
        raise HTTPException(status_code=400, detail=f"File content does not match expected type for '{ext}'")


@app.post("/portal/submit")
@limiter.limit("60/minute")
async def portal_submit(
    request: Request,
    file: UploadFile = File(...),
    roll: str = Form(...),
    name: str = Form(None),
    email: str = Form(None),
    access_code: str = Form(None),
    batch_id: str = Form(None),
):
    """Accept student submission and enqueue a processing job.

    Supports two modes:
    - Anonymous: provide access_code (looks up batch)
    - Authenticated: provide batch_id directly (JWT header optional, used to attach user_id)
    """
    if access_code:
        assignment = await run_db(get_assignment_by_access_code, access_code) if db_ready else None
        if not assignment:
            raise HTTPException(status_code=400, detail="Invalid access code")
        batch_id = assignment["batch_id"]
        user_id = None
    elif batch_id:
        assignment = await run_db(get_assignment, batch_id) if db_ready else None
        if not assignment:
            raise HTTPException(status_code=400, detail="Invalid batch_id")
        auth_header = request.headers.get("authorization", "")
        user_obj = get_optional_user(auth_header) if auth_header else None
        user_id = user_obj.get("user_id") if user_obj else None
    else:
        raise HTTPException(status_code=400, detail="Provide access_code or batch_id")

    content = await file.read()
    safe_filename = _sanitize_filename(file.filename or "upload")
    _validate_file(safe_filename, content)

    uploads_dir = os.getenv("UPLOAD_DIR", "/app/uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    try:
        usage = shutil.disk_usage(uploads_dir)
        if usage.used / usage.total > 0.95:
            raise HTTPException(status_code=507, detail="Insufficient storage")
    except HTTPException:
        raise
    except Exception:
        logging.warning("Failed to check disk usage")
    submission_hash = str(uuid.uuid4())
    filename = f"{batch_id}_{roll}_{submission_hash}_{safe_filename}"
    dest = os.path.join(uploads_dir, filename)
    with open(dest, "wb") as f:
        f.write(content)

    if db_ready:
        try:
            sub_result = await run_db(
                create_submission,
                submission_id=submission_hash,
                batch_id=batch_id,
                roll=roll,
                name=name,
                email=email,
                filename=filename,
                file_path=dest,
                user_id=locals().get('user_id'),
            )
            if sub_result["cancelled_submission_id"]:
                cancelled_path = sub_result["cancelled_file_path"]
                if cancelled_path and os.path.exists(cancelled_path):
                    try:
                        os.remove(cancelled_path)
                    except Exception:
                        logging.warning("Failed to remove old file: %s", cancelled_path)
                try:
                    update_job_status(sub_result["cancelled_submission_id"], JobStatus.CANCELLED.value)
                except Exception:
                    logging.warning("Failed to cancel previous job: %s", sub_result["cancelled_submission_id"])
        except Exception:
            logging.exception("Failed to persist submission %s", submission_hash)

    job = Job(job_id=submission_hash, text=dest)
    queued = await queue_client.enqueue_job(job)
    if db_ready:
        try:
            await run_db(
                create_job_record,
                job_id=submission_hash,
                text=dest,
                status=JobStatus.PENDING.value,
            )
        except Exception:
            logging.exception("Failed to create job record %s", submission_hash)

    try:
        await broadcast_progress(batch_id)
    except Exception:
        logging.exception("Failed to broadcast progress for batch %s", batch_id)

    audit("submission.create", actor=user_id or "anonymous", resource=submission_hash, detail={"batch_id": batch_id, "roll": roll})
    return {"submission_hash": submission_hash, "queued": bool(queued)}


@app.post("/portal/submissions/{submission_id}/cancel")
async def cancel_submission(submission_id: str, current_user: dict = Depends(get_current_user)):
    """Cancel a submission and delete its file if it is still active."""
    if not db_ready:
        raise HTTPException(status_code=503, detail="Database not ready")

    from shared.database import Submission, get_session

    with get_session() as session:
        record = session.get(Submission, submission_id)
        if not record:
            raise HTTPException(status_code=404, detail="Submission not found")
        if record.status != "ACTIVE":
            return {"submission_id": submission_id, "status": record.status}

        record.status = "CANCELLED"
        file_path = record.file_path

    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            logging.warning("Failed to remove file for cancelled submission %s", submission_id)

    try:
        update_job_status(submission_id, JobStatus.CANCELLED.value)
    except Exception:
        logging.warning("Failed to update job status for cancelled submission %s", submission_id)

    audit("submission.cancel", actor=current_user.get("user_id"), resource=submission_id)
    return {"submission_id": submission_id, "status": "CANCELLED"}


@app.get("/portal/my")
async def my_student_dashboard(current_user: dict = Depends(get_current_user)):
    """Return the student's own submissions grouped by batch (scoped student dashboard)."""
    if not db_ready:
        raise HTTPException(status_code=503, detail="Database not ready")

    from shared.database import get_submissions_by_user

    user_id = current_user.get("user_id")
    submissions = await run_db(get_submissions_by_user, user_id)

    # group by batch and fetch batch details
    from shared.database import get_assignment

    batches = {}
    for sub in submissions:
        bid = sub["batch_id"]
        if bid not in batches:
            assignment = get_assignment(bid) or {"name": "Unknown", "id": bid}
            batches[bid] = {
                "batch_id": bid,
                "name": assignment.get("name", "Unknown"),
                "submissions": [],
            }
        batches[bid]["submissions"].append(sub)

    return {"batches": list(batches.values()), "total": len(submissions)}


@app.websocket("/portal/ws/{batch_id}")
async def portal_ws(websocket: WebSocket, batch_id: str, token: str = ""):
    client_ip = websocket.client.host if websocket.client else "unknown"
    if not _check_ws_rate(client_ip):
        await websocket.close(code=4001)
        return
    if token:
        user_id = decode_access_token(token)
        if not user_id:
            await websocket.close(code=4001)
            return
    await websocket.accept()
    # register
    if batch_id not in ws_connections:
        ws_connections[batch_id] = set()
    ws_connections[batch_id].add(websocket)
    try:
        # send initial state
        await broadcast_progress(batch_id)
        while True:
            # keep connection alive
            msg = await websocket.receive_text()
            # echo or ignore
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        ws_connections[batch_id].discard(websocket)
    except Exception:
        ws_connections[batch_id].discard(websocket)


@app.post("/portal/compute-similarity/{batch_id}")
async def compute_similarity(batch_id: str, current_user: dict = Depends(get_current_user)):
    """Enqueue a batch-compute job for a batch to be processed asynchronously by workers."""
    assignment = await run_db(get_assignment, batch_id) if db_ready else None
    if not assignment:
        raise HTTPException(status_code=404, detail="Batch not found")

    submissions = await run_db(get_submissions_by_batch, batch_id) if db_ready else []
    if len(submissions) < 2:
        raise HTTPException(
            status_code=400,
            detail="Upload at least 2 submissions before computing similarity.",
        )

    job_id = f"batch-{batch_id}-{uuid.uuid4().hex[:8]}"
    payload = json.dumps({"type": "BATCH_COMPUTE", "batch_id": batch_id})
    job = Job(job_id=job_id, text=payload)

    queued = await queue_client.enqueue_job(job)
    if db_ready:
        try:
            await run_db(create_job_record, job_id=job_id, text=payload, status=JobStatus.PENDING.value)
        except Exception:
            logging.warning("Failed to create job record for batch compute %s", job_id)

    if not queued:
        raise HTTPException(status_code=500, detail="Failed to enqueue batch compute")

    audit("batch.compute", actor=current_user.get("user_id"), resource=batch_id)
    return {"job_id": job_id, "status": "queued"}


@app.get("/portal/similarity-matrix/{batch_id}")
async def get_batch_similarity_matrix(batch_id: str, current_user: dict = Depends(get_current_user)):
    """Retrieve pre-computed similarity matrix for a batch."""
    matrix = await run_db(get_similarity_matrix, batch_id)
    if not matrix:
        raise HTTPException(status_code=404, detail="Similarity matrix not computed")

    return {"batch_id": batch_id, "matrix": matrix}


@app.get("/portal/submissions/{batch_id}")
async def list_submissions(batch_id: str, current_user: dict = Depends(get_current_user), limit: int = 100, offset: int = 0):
    """List submissions for a batch from DB with pagination."""
    page = await run_db(get_submissions_by_batch, batch_id, limit=limit, offset=offset) if db_ready else []
    total = await run_db(get_submissions_count_by_batch, batch_id) if db_ready else len(page)
    return {
        "batch_id": batch_id,
        "submissions": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/portal/export/{batch_id}")
async def export_batch_csv(batch_id: str, current_user: dict = Depends(get_current_user)):
    """Export batch results (submissions + similarity scores) as CSV."""
    if db_ready:
        assignment = await run_db(get_assignment, batch_id)
        if not assignment:
            raise HTTPException(status_code=404, detail="Batch not found")

    submissions = await run_db(get_submissions_by_batch, batch_id) if db_ready else []
    if not submissions:
        raise HTTPException(status_code=400, detail="No submissions found")

    matrix = await run_db(get_similarity_matrix, batch_id) if db_ready else {}

    # build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # header
    writer.writerow(
        [
            "Roll Number",
            "Student Name",
            "Email",
            "Submission ID",
            "File Name",
            "Plagiarism Score",
            "AI Score",
            "Max Similarity",
            "Status",
        ]
    )

    # rows
    for sub in submissions:
        roll = sub.get("roll", "")
        name = sub.get("name", "")
        email = sub.get("email", "")
        sub_id = sub.get("submission_id", "")
        filename = sub.get("filename", "")
        plag_score = sub.get("plagiarism_score", 0) or 0
        ai_score = sub.get("ai_score", 0) or 0

        # find max similarity to any other submission
        max_sim = 0
        if sub["submission_id"] in matrix:
            for other_id, score in matrix[sub["submission_id"]].items():
                if other_id != sub["submission_id"]:
                    max_sim = max(max_sim, score)

        status = "Completed" if plag_score > 0 else "Pending"
        writer.writerow(
            [
                roll,
                name,
                email,
                sub_id,
                filename,
                f"{plag_score:.2f}",
                f"{ai_score:.2f}",
                f"{max_sim:.2f}",
                status,
            ]
        )

    # prepare streaming response
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=batch_{batch_id[:8]}_results.csv"
        },
    )


@app.get("/portal/submissions/{batch_id}/{submission_id}/text")
async def get_submission_text(batch_id: str, submission_id: str, current_user: dict = Depends(get_current_user)):
    """Extract and return text content of a submission."""
    subs = await run_db(get_submissions_by_batch, batch_id) if db_ready else []
    for sub in subs:
        if sub.get("submission_id") == submission_id:
            file_path = sub.get("file_path")
            if not file_path or not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="Submission file not found")
            text = extract_text(file_path)
            return {"submission_id": submission_id, "text": text, "roll": sub.get("roll")}
    raise HTTPException(status_code=404, detail="Submission not found")


@app.get("/debug/test-extraction/{batch_id}")
async def debug_extract_batch(batch_id: str, current_user: dict = Depends(get_current_user)):
    """Test endpoint: extract text from all submissions in a batch and test vectorization."""
    from pathlib import Path

    from docx import Document
    from pypdf import PdfReader

    # Get submissions
    subs = get_submissions_by_batch(batch_id)
    if not subs:
        return {"error": "No submissions found"}

    results = {"batch_id": batch_id, "submissions": []}

    def extract_text(file_path: str) -> str:
        """Extract text from file."""
        suffix = Path(file_path).suffix.lower()
        try:
            if suffix in {".txt", ".md", ".csv", ".py", ".java", ".js", ".ts"}:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            if suffix == ".pdf":
                reader = PdfReader(file_path)
                parts = []
                for page in reader.pages:
                    parts.append(page.extract_text() or "")
                return "\n".join(parts)
            if suffix == ".docx":
                doc = Document(file_path)
                return "\n".join(p.text for p in doc.paragraphs)
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            return f"ERROR: {str(e)}"

    vec = TextVectorizer()

    for sub in subs:
        fpath = sub["file_path"]
        sub_id = sub["submission_id"]
        text = extract_text(fpath)
        added = (
            vec.add_document(sub_id, text)
            if not isinstance(text, str) or not text.startswith("ERROR")
            else False
        )
        results["submissions"].append(
            {
                "submission_id": sub_id,
                "roll": sub.get("roll"),
                "name": sub.get("name"),
                "file_path": fpath,
                "file_exists": os.path.exists(fpath),
                "text_length": len(text) if not text.startswith("ERROR") else 0,
                "text_preview": text[:100] if not text.startswith("ERROR") else text,
                "added_to_vectorizer": added,
            }
        )

    # Try to compute similarity
    matrix = vec.compute_similarity_matrix()
    results["matrix"] = matrix
    results["doc_count"] = len(vec.doc_ids)

    return results


@app.get("/portal/report/{batch_id}/{sub_id_1}/{sub_id_2}")
async def download_report(
    batch_id: str,
    sub_id_1: str,
    sub_id_2: str,
    current_user: dict = Depends(get_current_user),
):
    """Generate and download a PDF similarity report for a pair of submissions."""
    assignment = await run_db(get_assignment, batch_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    sub_1 = await run_db(get_submission_by_id, sub_id_1)
    sub_2 = await run_db(get_submission_by_id, sub_id_2)
    if not sub_1 or not sub_2:
        raise HTTPException(status_code=404, detail="Submission not found")

    matrix = await run_db(get_similarity_matrix, batch_id)
    score = matrix.get(sub_id_1, {}).get(sub_id_2, 0.0)

    try:
        text_1 = extract_text(sub_1.get("file_path", ""))
    except Exception:
        text_1 = ""
    try:
        text_2 = extract_text(sub_2.get("file_path", ""))
    except Exception:
        text_2 = ""

    pdf_bytes = generate_similarity_report_pdf(
        batch_name=assignment.get("name", batch_id),
        submission_a=sub_1,
        submission_b=sub_2,
        similarity_score=score,
        text_a=text_1 or "",
        text_b=text_2 or "",
        ai_score_a=sub_1.get("ai_score"),
        ai_score_b=sub_2.get("ai_score"),
    )
    if not pdf_bytes:
        raise HTTPException(status_code=500, detail="PDF generation failed")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="report_{batch_id}_{sub_id_1}_vs_{sub_id_2}.pdf"'
        },
    )


@app.get("/portal/cross-batch/{batch_id_1}/{batch_id_2}")
async def cross_batch_comparison(
    batch_id_1: str,
    batch_id_2: str,
    current_user: dict = Depends(get_current_user),
):
    """Compare submissions across two different batches."""
    results = await run_db(get_cross_batch_comparisons, batch_id_1, batch_id_2)
    return {"batch_id_1": batch_id_1, "batch_id_2": batch_id_2, "comparisons": results}


@app.get("/portal/student-comparison/{submission_id}")
async def student_comparison(
    submission_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get comparison details for a single submission."""
    details = await run_db(get_student_comparison_details, submission_id)
    return {"submission_id": submission_id, "comparisons": details}


@app.post("/portal/external-lookup/{submission_id}")
async def external_lookup(
    submission_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Search external sources for similar content."""
    sub = await run_db(get_submission_by_id, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    try:
        text = extract_text(sub.get("file_path", ""))
    except Exception:
        text = ""
    if not text:
        raise HTTPException(status_code=400, detail="No text content found")

    results = search_external_sources(text)
    audit("external_lookup", actor=current_user.get("user_id"), detail={"submission_id": submission_id})
    return results


@app.post("/portal/notify-email/{submission_id}")
async def trigger_email_notification(
    submission_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Send an email notification about a completed submission."""
    sub = await run_db(get_submission_by_id, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    user = await run_db(get_user_by_id, current_user.get("user_id"))
    name = sub.get("name") or user.get("name") if user else "Student"
    email = sub.get("email") or user.get("email") if user else None
    if not email:
        raise HTTPException(status_code=400, detail="No email address available")

    ok = notify_completion(
        to=email,
        name=name,
        batch_name=sub.get("batch_id", "Assignment"),
        score=sub.get("plagiarism_score"),
    )
    if not ok:
        await run_db(create_notification, current_user.get("user_id"), email, "Analysis Complete", f"Your submission for {sub.get('batch_id')} has been analyzed.")
    return {"ok": ok, "email": email}


@app.get("/admin/stats")
async def admin_stats(current_user: dict = Depends(require_role("admin"))):
    """Get system-wide statistics."""
    stats = await run_db(get_admin_stats)
    return stats


@app.get("/admin/stats/export")
async def admin_stats_export(current_user: dict = Depends(require_role("admin"))):
    """Export admin stats as CSV."""
    stats = await run_db(get_admin_stats)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Metric", "Value"])
    for key, value in stats.items():
        writer.writerow([key.replace("_", " ").title(), value])
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=plagioscale_stats.csv"})


@app.get("/admin/users")
async def admin_list_users(
    current_user: dict = Depends(require_role("admin")),
    search: str = "",
    page: int = 1,
    per_page: int = 20,
):
    """List all users with pagination and search."""
    users = await run_db(lambda: get_paginated_users(search=search, page=page, per_page=per_page))
    return users


@app.post("/admin/users/{user_id}/role")
async def admin_update_role(
    user_id: str,
    body: dict,
    current_user: dict = Depends(require_role("admin")),
):
    """Update a user's role."""
    new_role = body.get("role", "user")
    if new_role not in ("user", "teacher", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    ok = await run_db(update_user_role, user_id, new_role)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@app.post("/admin/notifications/send")
async def admin_send_notifications(current_user: dict = Depends(require_role("admin"))):
    """Send all pending email notifications."""
    pending = await run_db(get_pending_notifications, 50)
    sent_count = 0
    for n in pending:
        ok = send_email(
            to=n["email"] or "",
            subject=n["subject"],
            body_text=n["body"],
        )
        if ok:
            await run_db(mark_notification_sent, n["id"])
            sent_count += 1
    return {"ok": True, "sent": sent_count, "pending": len(pending)}


AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "/app/logs/audit.log")


@app.get("/admin/audit/tail")
async def admin_audit_tail(current_user: dict = Depends(require_role("admin"))):
    """SSE endpoint that tails the audit log in real time."""
    async def event_stream():
        try:
            with open(AUDIT_LOG_PATH, "r") as f:
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if line:
                        yield f"data: {line.strip()}\n\n"
                    else:
                        await asyncio.sleep(0.5)
        except FileNotFoundError:
            yield "event: error\ndata: Audit log not found\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/webhooks/alertmanager")
async def alertmanager_webhook(payload: dict):
    """Receive Alertmanager webhook notifications and trigger auto-remediation."""
    alerts = payload.get("alerts", [])
    for alert in alerts:
        status = alert.get("status")
        alertname = alert.get("labels", {}).get("alertname", "unknown")
        logging.info(f"Alertmanager webhook: {alertname} ({status})")
        if status == "firing":
            job = alert.get("labels", {}).get("job", "")
            if "ServiceDown" in alertname and "api" not in job:
                AUTO_RECOVERY_TOTAL.labels("alert_restart").inc()
                logging.info(f"Auto-remediation triggered for {job}")
    return {"ok": True, "received": len(alerts)}


if __name__ == "__main__":
    import uvicorn

    ssl_kwargs = {}
    if os.getenv("USE_MTLS", "").lower() in ("true", "1"):
        ssl_kwargs.update(
            ssl_certfile="/app/certs/api.crt",
            ssl_keyfile="/app/certs/api.key",
            ssl_ca_certs="/app/certs/ca.crt",
            ssl_cert_reqs=2,
        )

    uvicorn.run(app, host="0.0.0.0", port=8000, **ssl_kwargs)
