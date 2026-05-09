"""
FastAPI service for PlagioScale - accepts plagiarism detection requests and queues them.
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import sys
import os
import uuid
from pydantic import BaseModel
from prometheus_client import make_asgi_app, Counter, Gauge

# Add shared to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.models import Job, JobStatus
from shared.queue_client import QueueClient
from shared.database import create_job_record, get_job_record, init_db

app = FastAPI(title="PlagioScale API", version="1.0.0")
# Prometheus metrics
REQUESTS_SUBMITTED = Counter('plagioscale_requests_submitted_total', 'Total submitted jobs')
QUEUE_LENGTH_GAUGE = Gauge('plagioscale_queue_length', 'Current Redis queue length')

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
        raise HTTPException(status_code=400, detail="Text must be at least 10 characters")
    
    job_id = str(uuid.uuid4())
    job = Job(job_id=job_id, text=request.text)
    
    if queue_client.enqueue_job(job):
        if db_ready:
            create_job_record(job_id=job_id, text=request.text, status=JobStatus.PENDING.value)
        REQUESTS_SUBMITTED.inc()
        return {
            "job_id": job_id,
            "status": "submitted",
            "message": "Job queued for processing"
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
    
    return {
        "job_id": job_id,
        "status": status,
        "result": result
    }


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
    
    return {
        "job_id": job_id,
        "status": status
    }


@app.get("/queue/stats")
async def queue_stats():
    """Get queue statistics."""
    queue_length = queue_client.get_queue_length()
    try:
        QUEUE_LENGTH_GAUGE.set(queue_length)
    except Exception:
        pass
    return {
        "queue_length": queue_length,
        "message": f"{queue_length} jobs waiting"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
