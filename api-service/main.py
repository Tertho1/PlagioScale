"""
FastAPI service for PlagioScale - accepts plagiarism detection requests and queues them.
"""

from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File,
    Form,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import sys
import os
import uuid
from pydantic import BaseModel
from prometheus_client import make_asgi_app, Counter, Gauge
import json
import csv
import io

# Add shared to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.models import Job, JobStatus
from shared.queue_client import QueueClient
from shared.database import (
    create_job_record,
    get_job_record,
    init_db,
    create_assignment as db_create_assignment,
    create_submission,
    get_submissions_by_batch,
    store_similarity_results,
    get_similarity_matrix,
    store_submission_embedding,
    get_assignment,
    get_assignment_by_access_code,
)
from shared.vectorizer import TextVectorizer
from datetime import datetime
import asyncio

# Websocket connections per batch (kept in-memory for active sockets)
ws_connections = {}

app = FastAPI(title="PlagioScale API", version="1.0.0")

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
queue_client = QueueClient()
db_ready = init_db()


class SubmitRequest(BaseModel):
    """Request to submit text for plagiarism detection."""

    text: str


class ResultResponse(BaseModel):
    """Response with job result."""

    job_id: str
    status: str
    result: dict = None
    error: str = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "api-service"}


@app.post("/submit")
async def submit_text(request: SubmitRequest):
    """
    Submit text for plagiarism detection.

    Returns job_id for later result retrieval.
    """
    if not request.text or len(request.text.strip()) < 10:
        raise HTTPException(
            status_code=400, detail="Text must be at least 10 characters"
        )

    job_id = str(uuid.uuid4())
    job = Job(job_id=job_id, text=request.text)

    if queue_client.enqueue_job(job):
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

    status = queue_client.get_job_status(job_id)

    if not status:
        raise HTTPException(status_code=404, detail="Job not found")

    result = queue_client.get_result(job_id)

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
            }

    status = queue_client.get_job_status(job_id)

    if not status:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"job_id": job_id, "status": status}


@app.get("/queue/stats")
async def queue_stats():
    """Get queue statistics."""
    queue_length = queue_client.get_queue_length()
    try:
        QUEUE_LENGTH_GAUGE.set(queue_length)
    except Exception:
        pass
    return {"queue_length": queue_length, "message": f"{queue_length} jobs waiting"}


@app.post("/portal/assignments")
async def create_assignment(body: dict):
    """Create a new assignment/batch and return batch_id and access_code."""
    name = body.get("name") or body.get("assignment") or "Assignment"
    expected = int(body.get("expected_count", 0) or 0)
    batch_id = str(uuid.uuid4())
    access_code = uuid.uuid4().hex[:8]
    # prepare websocket set (in-memory sockets only)
    ws_connections[batch_id] = set()
    # persist to DB
    if db_ready:
        try:
            db_create_assignment(
                batch_id=batch_id,
                name=name,
                access_code=access_code,
                expected_count=expected,
            )
        except Exception:
            pass
    return {"batch_id": batch_id, "access_code": access_code}


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
        total = 0
    try:
        subs = get_submissions_by_batch(batch_id) if db_ready else []
        processed = len(subs)
    except Exception:
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


@app.post("/portal/submit")
async def portal_submit(
    file: UploadFile = File(...),
    roll: str = Form(...),
    name: str = Form(None),
    access_code: str = Form(...),
):
    """Accept student submission and enqueue a processing job."""
    # find batch by access_code (DB-backed)
    assignment = get_assignment_by_access_code(access_code) if db_ready else None
    if not assignment:
        raise HTTPException(status_code=400, detail="Invalid access code")
    batch_id = assignment["batch_id"]

    # save file
    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    filename = f"{batch_id}_{roll}_{file.filename}"
    dest = os.path.join(uploads_dir, filename)
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    submission_hash = str(uuid.uuid4())
    entry = {
        "submission_hash": submission_hash,
        "roll": roll,
        "name": name,
        "filename": filename,
        "path": dest,
        "created_at": datetime.utcnow().isoformat(),
    }
    # persist submission to DB
    if db_ready:
        try:
            create_submission(
                submission_id=submission_hash,
                batch_id=batch_id,
                roll=roll,
                name=name,
                filename=filename,
                file_path=dest,
            )
        except Exception:
            pass

    # Enqueue job: use submission_hash as job_id and store file path in text field
    job = Job(job_id=submission_hash, text=dest)
    queued = queue_client.enqueue_job(job)
    if db_ready:
        try:
            create_job_record(
                job_id=submission_hash, text=dest, status=JobStatus.PENDING.value
            )
        except Exception:
            pass

    # broadcast progress to teacher dashboard
    try:
        await broadcast_progress(batch_id)
    except Exception:
        pass

    return {"submission_hash": submission_hash, "queued": bool(queued)}


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

    queued = queue_client.enqueue_job(job)
    if db_ready:
        try:
            create_job_record(
                job_id=job_id, text=payload, status=JobStatus.PENDING.value
            )
        except Exception:
            pass

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
async def list_submissions(batch_id: str):
    """List submissions for a batch from DB."""
    subs = get_submissions_by_batch(batch_id)
    return {"batch_id": batch_id, "submissions": subs}


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


@app.get("/debug/test-extraction/{batch_id}")
async def debug_extract_batch(batch_id: str):
    """Test endpoint: extract text from all submissions in a batch and test vectorization."""
    from pathlib import Path
    from shared.vectorizer import TextVectorizer
    from pypdf import PdfReader
    from docx import Document

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
