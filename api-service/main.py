"""PlagioScale API service."""

import asyncio
import csv
import io
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from prometheus_client import Counter, Gauge, make_asgi_app
from pydantic import BaseModel, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

# Add shared to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from typing import Optional as _Optional

from jose import JWTError, jwt
import bcrypt as _bcrypt

from shared.database import (
    create_assignment as db_create_assignment,
)
from shared.database import (
    create_job_record,
    create_submission,
    create_user,
    get_active_submission_by_batch_and_roll,
    get_assignment,
    get_assignment_by_access_code,
    get_job_record,
    get_similarity_matrix,
    get_submissions_by_batch,
    get_user_by_email,
    get_user_by_id,
    init_db,
    list_assignments,
    update_job_status,
    update_submission_status,
)
from shared.models import Job, JobStatus
from shared.queue_client import AsyncQueueClient
from shared.text_extraction import extract_text
from shared.vectorizer import TextVectorizer

# Websocket connections per batch (kept in-memory for active sockets)
ws_connections = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(title="PlagioScale API", version="1.0.0")


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


@app.on_event("startup")
async def _start_ws_cleanup():
    asyncio.create_task(_cleanup_stale_ws())
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
JWT_SECRET = os.getenv("JWT_SECRET", "please-change-this-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

_ENV = os.getenv("ENV", "development")
if _ENV == "production" and JWT_SECRET == "please-change-this-secret":
    raise RuntimeError("JWT_SECRET must be changed in production mode")


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


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    data = {"sub": subject, "exp": expire}
    token = jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def decode_access_token(token: str) -> _Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """Resolve the current user from a Bearer JWT."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[len(prefix) :].strip()
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = get_user_by_id(user_id) if db_ready else {"user_id": user_id}
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user





@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "api-service"}


@app.post("/submit")
@limiter.limit("30/minute")
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
                job_id=job_id, text=request.text, status=JobStatus.PENDING.value
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
    # Check existing
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

    token = create_access_token(user_id)
    return {"access_token": token, "token_type": "bearer"}


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

    token = create_access_token(user.get("user_id"))
    return {"access_token": token, "token_type": "bearer"}


@app.post("/auth/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def auth_refresh(request: Request, authorization: str | None = Header(default=None)):
    """Issue a new access token from a valid existing one."""
    user = get_current_user(authorization)
    token = create_access_token(user.get("user_id"))
    return {"access_token": token, "token_type": "bearer"}




@app.post("/portal/assignments")
async def create_assignment(body: dict, current_user: dict = Depends(get_current_user)):
    """Create a new assignment/batch and return batch_id and access_code."""
    name = body.get("name") or body.get("assignment") or "Assignment"
    expected = int(body.get("expected_count", 0) or 0)
    batch_id = str(uuid.uuid4())
    access_code = uuid.uuid4().hex[:8]
    # prepare websocket set (in-memory sockets only)
    ws_connections[batch_id] = set()
    # persist to DB
    if db_ready:
        ok = db_create_assignment(
            batch_id=batch_id,
            name=name,
            access_code=access_code,
            expected_count=expected,
            owner_user_id=current_user.get("user_id"),
        )
        if not ok:
            raise HTTPException(
                status_code=500,
                detail="Failed to create assignment — database write failed",
            )
    return {"batch_id": batch_id, "access_code": access_code}


@app.get("/portal/assignments")
async def list_portal_assignments(current_user: dict = Depends(get_current_user)):
    """List assignments for the dashboard."""
    assignments = list_assignments() if db_ready else []
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
    assignment = get_assignment(batch_id) if db_ready else None
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    submissions = get_submissions_by_batch(batch_id) if db_ready else []
    matrix = get_similarity_matrix(batch_id) if db_ready else {}
    return {
        "assignment": assignment,
        "submissions": submissions,
        "similarity_matrix_ready": bool(matrix),
        "submissions_count": len(submissions),
    }


async def broadcast_progress(batch_id: str):
    """Send progress updates to all connected websockets for a batch."""
    if batch_id not in ws_connections:
        return
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
    """
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
        raise HTTPException(status_code=500, detail=str(e))


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".py", ".java", ".js", ".ts"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

FILE_MAGIC_BYTES = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",
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
        assignment = get_assignment_by_access_code(access_code) if db_ready else None
        if not assignment:
            raise HTTPException(status_code=400, detail="Invalid access code")
        batch_id = assignment["batch_id"]
        user_id = None
    elif batch_id:
        assignment = get_assignment(batch_id) if db_ready else None
        if not assignment:
            raise HTTPException(status_code=400, detail="Invalid batch_id")
        # try to extract user from JWT if present
        try:
            auth_header = request.headers.get("authorization")
            if auth_header:
                from jose import jwt as jose_jwt
                payload = jose_jwt.decode(auth_header.replace("Bearer ", ""), JWT_SECRET, algorithms=["HS256"])
                user_id = payload.get("sub")
            else:
                user_id = None
        except Exception:
            user_id = None
    else:
        raise HTTPException(status_code=400, detail="Provide access_code or batch_id")

    previous_submission = (
        get_active_submission_by_batch_and_roll(batch_id, roll) if db_ready and access_code else None
    )

    content = await file.read()
    safe_filename = _sanitize_filename(file.filename or "upload")
    _validate_file(safe_filename, content)

    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    submission_hash = str(uuid.uuid4())
    filename = f"{batch_id}_{roll}_{submission_hash}_{safe_filename}"
    dest = os.path.join(uploads_dir, filename)
    with open(dest, "wb") as f:
        f.write(content)

    if db_ready:
        try:
            create_submission(
                submission_id=submission_hash,
                batch_id=batch_id,
                roll=roll,
                name=name,
                email=email,
                filename=filename,
                file_path=dest,
                user_id=locals().get('user_id'),
            )
            if previous_submission:
                update_submission_status(previous_submission["submission_id"], "CANCELLED")
                old_path = previous_submission.get("file_path")
                if old_path and os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except Exception:
                        logging.warning("Failed to remove old file: %s", old_path)
                try:
                    update_job_status(previous_submission["submission_id"], JobStatus.CANCELLED.value, worker_id=None)
                except Exception:
                    logging.warning("Failed to cancel previous job: %s", previous_submission["submission_id"])
        except Exception:
            logging.exception("Failed to persist submission %s", submission_hash)

    job = Job(job_id=submission_hash, text=dest)
    queued = await queue_client.enqueue_job(job)
    if db_ready:
        try:
            create_job_record(
                job_id=submission_hash, text=dest, status=JobStatus.PENDING.value
            )
        except Exception:
            logging.exception("Failed to create job record %s", submission_hash)

    try:
        await broadcast_progress(batch_id)
    except Exception:
        logging.exception("Failed to broadcast progress for batch %s", batch_id)

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

    return {"submission_id": submission_id, "status": "CANCELLED"}


@app.get("/portal/my")
async def my_student_dashboard(current_user: dict = Depends(get_current_user)):
    """Return the student's own submissions grouped by batch (scoped student dashboard)."""
    if not db_ready:
        raise HTTPException(status_code=503, detail="Database not ready")

    from shared.database import get_submissions_by_user

    user_id = current_user.get("user_id")
    submissions = get_submissions_by_user(user_id)

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
async def portal_ws(websocket: WebSocket, batch_id: str):
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
async def compute_similarity(batch_id: str):
    """Enqueue a batch-compute job for a batch to be processed asynchronously by workers."""
    # ensure batch exists
    assignment = get_assignment(batch_id) if db_ready else None
    if not assignment:
        raise HTTPException(status_code=404, detail="Batch not found")

    submissions = get_submissions_by_batch(batch_id) if db_ready else []
    if len(submissions) < 2:
        raise HTTPException(
            status_code=400,
            detail="Upload at least 2 submissions before computing similarity.",
        )

    # create a batch compute job payload
    job_id = f"batch-{batch_id}-{uuid.uuid4().hex[:8]}"
    payload = json.dumps({"type": "BATCH_COMPUTE", "batch_id": batch_id})
    job = Job(job_id=job_id, text=payload)

    queued = await queue_client.enqueue_job(job)
    if db_ready:
        try:
            create_job_record(
                job_id=job_id, text=payload, status=JobStatus.PENDING.value
            )
        except Exception:
            logging.warning("Failed to create job record for batch compute %s", job_id)

    if not queued:
        raise HTTPException(status_code=500, detail="Failed to enqueue batch compute")

    return {"job_id": job_id, "status": "queued"}


@app.get("/portal/similarity-matrix/{batch_id}")
async def get_batch_similarity_matrix(batch_id: str):
    """Retrieve pre-computed similarity matrix for a batch."""
    matrix = get_similarity_matrix(batch_id)
    if not matrix:
        raise HTTPException(status_code=404, detail="Similarity matrix not computed")

    return {"batch_id": batch_id, "matrix": matrix}


@app.get("/portal/submissions/{batch_id}")
async def list_submissions(batch_id: str, limit: int = 100, offset: int = 0):
    """List submissions for a batch from DB with pagination."""
    all_subs = get_submissions_by_batch(batch_id)
    page = all_subs[offset:offset + limit]
    return {
        "batch_id": batch_id,
        "submissions": page,
        "total": len(all_subs),
        "limit": limit,
        "offset": offset,
    }


@app.get("/portal/export/{batch_id}")
async def export_batch_csv(batch_id: str):
    """Export batch results (submissions + similarity scores) as CSV."""
    if db_ready:
        assignment = get_assignment(batch_id)
        if not assignment:
            raise HTTPException(status_code=404, detail="Batch not found")

    # fetch submissions
    submissions = get_submissions_by_batch(batch_id)
    if not submissions:
        raise HTTPException(status_code=400, detail="No submissions found")

    # fetch similarity matrix
    matrix = get_similarity_matrix(batch_id)

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
async def get_submission_text(batch_id: str, submission_id: str):
    """Extract and return text content of a submission."""
    subs = get_submissions_by_batch(batch_id) if db_ready else []
    for sub in subs:
        if sub.get("submission_id") == submission_id:
            file_path = sub.get("file_path")
            if not file_path or not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="Submission file not found")
            text = extract_text(file_path)
            return {"submission_id": submission_id, "text": text, "roll": sub.get("roll")}
    raise HTTPException(status_code=404, detail="Submission not found")


@app.get("/debug/test-extraction/{batch_id}")
async def debug_extract_batch(batch_id: str):
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
