"""
FastAPI service for PlagioScale - accepts plagiarism detection requests and queues them.
"""
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.models import Job, JobStatus
from shared.queue_client import QueueClient
from shared.database import (create_job_record, get_job_record, init_db, 
                             create_assignment, create_submission, get_submissions_by_batch,
                             store_similarity_results, get_similarity_matrix, store_submission_embedding)
from shared.vectorizer import TextVectorizer
from datetime import datetime
import asyncio

# Simple in-memory store for assignments and websocket connections (demo)
assignments = {}
ws_connections = {}

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


@app.post('/portal/assignments')
async def create_assignment(body: dict):
    """Create a new assignment/batch and return batch_id and access_code."""
    name = body.get('name') or body.get('assignment') or 'Assignment'
    expected = int(body.get('expected_count', 0) or 0)
    batch_id = str(uuid.uuid4())
    access_code = uuid.uuid4().hex[:8]
    assignments[batch_id] = {
        'name': name,
        'expected_count': expected,
        'access_code': access_code,
        'created_at': datetime.utcnow().isoformat(),
        'submissions': []
    }
    # prepare websocket set
    ws_connections[batch_id] = set()
    # persist to DB
    if db_ready:
        try:
            create_assignment(batch_id=batch_id, name=name, access_code=access_code, expected_count=expected)
        except Exception:
            pass
    return {'batch_id': batch_id, 'access_code': access_code}


async def broadcast_progress(batch_id: str):
    """Send progress updates to all connected websockets for a batch."""
    if batch_id not in ws_connections:
        return
    total = assignments.get(batch_id, {}).get('expected_count', 0)
    processed = len(assignments.get(batch_id, {}).get('submissions', []))
    payload = {'processed': processed, 'total': total}
    dead = []
    for ws in list(ws_connections.get(batch_id, [])):
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for d in dead:
        ws_connections[batch_id].discard(d)


@app.post('/portal/submit')
async def portal_submit(file: UploadFile = File(...), roll: str = Form(...), name: str = Form(None), access_code: str = Form(...)):
    """Accept student submission and enqueue a processing job."""
    # find batch by access_code
    batch_id = None
    for b_id, meta in assignments.items():
        if meta.get('access_code') == access_code:
            batch_id = b_id
            break
    if not batch_id:
        raise HTTPException(status_code=400, detail='Invalid access code')

    # save file
    uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)
    filename = f"{batch_id}_{roll}_{file.filename}"
    dest = os.path.join(uploads_dir, filename)
    with open(dest, 'wb') as f:
        content = await file.read()
        f.write(content)

    submission_hash = str(uuid.uuid4())
    entry = {
        'submission_hash': submission_hash,
        'roll': roll,
        'name': name,
        'filename': filename,
        'path': dest,
        'created_at': datetime.utcnow().isoformat()
    }
    assignments[batch_id]['submissions'].append(entry)

    # persist submission to DB
    if db_ready:
        try:
            create_submission(submission_id=submission_hash, batch_id=batch_id, roll=roll, name=name, filename=filename, file_path=dest)
        except Exception:
            pass

    # Enqueue job: use submission_hash as job_id and store file path in text field
    job = Job(job_id=submission_hash, text=dest)
    queued = queue_client.enqueue_job(job)
    if db_ready:
        try:
            create_job_record(job_id=submission_hash, text=dest, status=JobStatus.PENDING.value)
        except Exception:
            pass

    # broadcast progress to teacher dashboard
    try:
        await broadcast_progress(batch_id)
    except Exception:
        pass

    return {'submission_hash': submission_hash, 'queued': bool(queued)}


@app.websocket('/portal/ws/{batch_id}')
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


@app.post('/portal/compute-similarity/{batch_id}')
async def compute_similarity(batch_id: str):
    """Compute similarity matrix for a batch by vectorizing all submissions."""
    # fetch submissions from DB
    submissions = get_submissions_by_batch(batch_id)
    if not submissions:
        raise HTTPException(status_code=400, detail='No submissions found')

    # initialize vectorizer
    vectorizer = TextVectorizer()

    # vectorize each submission text
    for sub in submissions:
        try:
            with open(sub['file_path'], 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            vectorizer.add_document(sub['submission_id'], text)
        except Exception as e:
            print(f"[Similarity] Error reading file {sub.get('file_path')}: {e}")

    # compute similarity matrix
    try:
        similarity_matrix = vectorizer.compute_similarity_matrix()
        if similarity_matrix:
            store_similarity_results(batch_id, similarity_matrix)
    except Exception as e:
        print(f"[Similarity] Error computing matrix: {e}")
        raise HTTPException(status_code=500, detail=f'Error computing similarity: {e}')

    return {
        'batch_id': batch_id,
        'num_submissions': len(submissions),
        'status': 'completed',
        'similarity_matrix': similarity_matrix
    }


@app.get('/portal/similarity-matrix/{batch_id}')
async def get_batch_similarity_matrix(batch_id: str):
    """Retrieve pre-computed similarity matrix for a batch."""
    matrix = get_similarity_matrix(batch_id)
    if not matrix:
        raise HTTPException(status_code=404, detail='Similarity matrix not computed')

    return {'batch_id': batch_id, 'matrix': matrix}


@app.get('/portal/submissions/{batch_id}')
async def list_submissions(batch_id: str):
    """List submissions for a batch from DB."""
    subs = get_submissions_by_batch(batch_id)
    return {'batch_id': batch_id, 'submissions': subs}


@app.get('/portal/export/{batch_id}')
async def export_batch_csv(batch_id: str):
    """Export batch results (submissions + similarity scores) as CSV."""
    if batch_id not in assignments:
        raise HTTPException(status_code=404, detail='Batch not found')
    
    # fetch submissions
    submissions = get_submissions_by_batch(batch_id)
    if not submissions:
        raise HTTPException(status_code=400, detail='No submissions found')
    
    # fetch similarity matrix
    matrix = get_similarity_matrix(batch_id)
    
    # build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # header
    writer.writerow(['Roll Number', 'Student Name', 'Plagiarism Score', 'AI Score', 'Max Similarity', 'Status'])
    
    # rows
    for sub in submissions:
        roll = sub.get('roll', '')
        name = sub.get('name', '')
        plag_score = sub.get('plagiarism_score', 0) or 0
        ai_score = sub.get('ai_score', 0) or 0
        
        # find max similarity to any other submission
        max_sim = 0
        if sub['submission_id'] in matrix:
            for other_id, score in matrix[sub['submission_id']].items():
                if other_id != sub['submission_id']:
                    max_sim = max(max_sim, score)
        
        status = 'Completed' if plag_score > 0 else 'Pending'
        writer.writerow([roll, name, f'{plag_score:.2f}', f'{ai_score:.2f}', f'{max_sim:.2f}', status])
    
    # prepare streaming response
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename=batch_{batch_id[:8]}_results.csv'}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
