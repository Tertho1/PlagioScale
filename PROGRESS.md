# PlagioScale Progress

**Overall progress: ~78% complete**

This is an estimate based on the current codebase and the features already wired up.

## Fully implemented
- [x] FastAPI API service
- [x] Worker service with text extraction and similarity pipeline
- [x] Redis queue + Postgres persistence
- [x] Docker Compose stack for the core services
- [x] JWT auth + general account login/signup
- [x] Submission replacement/cancel flow
- [x] Assignment creation, submission, compute, and matrix endpoints
- [x] Frontend rebuild flow through Docker

## Partially implemented
- [~] General dashboard UX and assignment drill-down
- [~] Homepage polish and app shell
- [~] Monitoring/observability wiring
- [~] Role-neutral product flow
- [~] Submission metadata display in the review view

## Not implemented yet
- [ ] Assignment attachments
- [ ] End-to-end automated tests
- [ ] Classroom-style assignment sections like pending/past/created-by-me
- [ ] Optional Nginx gateway layer beyond the current frontend container
- [ ] K3s / Kubernetes migration

## Progress by area
- **Backend/API:** ~90%
- **Worker/NLP pipeline:** ~90%
- **Data layer/queue:** ~90%
- **Frontend/product UX:** ~70%
- **Monitoring/ops:** ~60%
- **Testing:** ~10%

## What is left
- [ ] Add assignment attachments
- [ ] Finish dashboard UX so it feels more like a real workspace
- [ ] Add E2E tests
- [ ] Polish monitoring and deployment story
