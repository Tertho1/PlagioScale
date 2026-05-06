# PlagioScale - Cloud-Native Plagiarism Detection System

A distributed, cloud-native plagiarism detection system built with microservices architecture, queue-based processing, and autoscaling capabilities.

## Architecture

```
User → API Service (FastAPI) → Redis Queue → Worker(s) → Storage
                                    ↑
                              Autoscaler
```

### Components

- **API Service** (FastAPI): Accepts plagiarism detection requests, enqueues jobs, returns results
- **Worker Service** (Python): Processes jobs from queue using k-shingle + cosine similarity algorithms
- **Redis**: Message queue storing pending jobs and job metadata
- **Autoscaler**: Monitors queue length and scales workers automatically
- **Storage**: SQLite + JSON files for job results

## Job Lifecycle

Jobs flow through states: `PENDING → PROCESSING → COMPLETED → FAILED`

## Quick Start

### Prerequisites
- Docker Desktop
- Python 3.11+

### 1. Build and Start Services

```bash
docker-compose up --build
```

This starts:
- Redis on port 6379
- API Service on port 8000
- 1 Worker instance

### 2. Submit a Plagiarism Detection Request

```bash
curl -X POST http://localhost:8000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "Your text to check for plagiarism"}'
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "submitted",
  "message": "Job queued for processing"
}
```

### 3. Check Job Status

```bash
curl http://localhost:8000/status/{job_id}
```

### 4. Retrieve Results

```bash
curl http://localhost:8000/result/{job_id}
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "COMPLETED",
  "result": {
    "max_plagiarism_score": 0.7234,
    "avg_plagiarism_score": 0.5123,
    "comparison_results": [...]
  }
}
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/submit` | Submit text for plagiarism detection |
| GET | `/result/{job_id}` | Get job result |
| GET | `/status/{job_id}` | Get job status |
| GET | `/queue/stats` | Get queue statistics |
| GET | `/health` | Health check |

## Testing with Stress Test

Run the stress testing script to simulate multiple requests:

```bash
# Submit 50 jobs with 5 concurrent threads
python stress_test.py 50 5
```

This will:
1. Submit 50 plagiarism detection jobs
2. Monitor queue stats
3. Wait for completion and report results
4. Show throughput metrics

## Scaling Workers

Scale up to 3 workers:

```bash
docker-compose up --scale worker=3
```

Scale down to 1 worker:

```bash
docker-compose up --scale worker=1
```

## Project Structure

```
PlagioScale/
├── api-service/
│   ├── main.py              # FastAPI application
│   ├── requirements.txt      # Python dependencies
│   └── Dockerfile            # Container image
├── worker-service/
│   ├── worker.py            # Worker process
│   ├── requirements.txt      # Python dependencies
│   └── Dockerfile            # Container image
├── autoscaler/              # Auto-scaling logic (Phase 4)
├── shared/
│   ├── models.py            # Job schema and lifecycle
│   ├── queue_client.py      # Redis queue abstraction
│   └── plagiarism.py        # NLP detection engine
├── storage/                 # Results storage
├── docker-compose.yml       # Multi-container orchestration
└── stress_test.py           # Load testing script
```

## Technology Stack

- **Framework**: FastAPI
- **Queue**: Redis
- **Container**: Docker & Docker Compose
- **Language**: Python 3.11
- **Algorithm**: k-Shingle + Cosine Similarity

## Next Steps

Phase 2+:
- [ ] Autoscaler with queue-based scaling
- [ ] Prometheus + Grafana monitoring
- [ ] Nginx reverse proxy
- [ ] Kubernetes (K3s) migration
- [ ] S3 storage integration

## Roadmap to A+ Grade

✅ Phase 1: Microservices + Queue + Job Lifecycle
🔄 Phase 2-3: Docker + docker-compose (local cloud)
📊 Phase 4: Autoscaler (queue-driven)
📈 Phase 5: Monitoring (Prometheus + Grafana)
🚀 Phase 6: Kubernetes (K3s)
