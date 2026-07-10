# PlagioScale — Agent Context

## Project Overview

PlagioScale is a cloud-native, microservices-based plagiarism detection platform that runs entirely locally via Docker Compose. No cloud services, no paid APIs.

## Stack

- **Backend:** Python FastAPI (4 services: api, worker, autoscaler, monitoring)
- **Frontend:** React + Vite (served via Nginx)
- **Database:** PostgreSQL 16 (Docker)
- **Queue:** Redis 7 (Docker)
- **Monitoring:** Prometheus + Grafana
- **Auth:** JWT (bcrypt passwords)

## Key Architecture Decisions

| Decision | Choice |
|---|---|
| Async Redis in API | Implemented — `AsyncQueueClient` in `shared/queue_client.py` (Phase 2) |
| Autoscaler | In-container (Docker SDK) — host variant (`infrastructure/`) pending deletion (Round 2) |
| JWT storage | localStorage (XSS-vulnerable — acceptable for local demo) |
| WebSocket scaling | Single API instance only — no Redis Pub/Sub for multi-replica yet |
| Resource limits | Set on all services in docker-compose.yml (Phase 0) |

## Known Bugs (audit July 2026)

| ID | Bug | Severity | Round |
|---|---|---|---|
| A | `get_user_by_email` missing `password_hash` — login broken for all users | 🔴 HIGH | Round 1 |
| B | `create_assignment` returns success on silent DB write failure | 🟠 MEDIUM | Round 1 |
| C | `StudentDashboard.jsx` upload missing required `roll` field → 422 | 🟠 MEDIUM | Round 1 |

See `TODO.md` for full 4-round fix plan.

## Folder Structure

```
api-service/         # FastAPI REST API (port 8000)
worker-service/      # Background job processor (port 8001)
autoscaler/          # In-container autoscaler (port 8002)
monitoring-service/  # Live monitoring dashboard (port 8090)
shared/              # Python modules shared across all services
frontend/            # React + Vite + Nginx (port 3050)
scripts/             # Utility scripts (stress test, seed data, pg_backup)
infrastructure/      # Legacy scripts (marked for deletion in Round 2)
docs/                # Planning docs + archived reports
prometheus/          # Prometheus scrape config
grafana/             # Pre-provisioned dashboards
```


