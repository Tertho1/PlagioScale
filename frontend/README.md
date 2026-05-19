PlagioScale Frontend — React + Vite

A modern React app for interacting with PlagioScale plagiarism detection API.

Tech Stack:
- React 18
- Vite 8 (build tool)
- Vanilla CSS (no extra CSS framework)
- localStorage for job history

## Development

```bash
npm install
npm run dev
```

If you do not have Node installed locally, you can run the same commands in Docker:

```bash
docker run --rm -v D:\PlagioScale\frontend:/app -w /app node:24-slim sh -lc "npm install && npm run build"
```

Visit `http://localhost:5173` in your browser. The frontend will proxy API calls to `http://localhost:8000` (configurable via VITE_API_BASE env).

## Portal Mode

This frontend now includes two portal experiences:

- `/` — Student submission portal (enter name, roll, access code, upload file)
- `/teacher` — Teacher dashboard (create assignments, view progress, similarity matrix placeholder)

The frontend expects the following backend endpoints (placeholders you should implement in the API):

- `POST /portal/assignments` -> create assignment, returns `{ batch_id, access_code }`
- `POST /portal/submit` -> accepts `multipart/form-data` with `file`, `roll`, `name`, `access_code`; returns `{ submission_hash }`
- `WS  /portal/ws/{batch_id}` -> websocket for batch progress updates

For faster iteration during development set `VITE_API_BASE` in `.env`.

## Production Build

```bash
npm run build
```

Outputs to `dist/` folder, ready to be served.

## Docker Build

```bash
docker build -t plagioscale-frontend:latest ./frontend
docker run -p 3000:80 plagioscale-frontend:latest
```

## Features

- Submit text for plagiarism analysis
- Job list with real-time status polling (every 30s)
- View detailed result for completed jobs
- localStorage persistence of recent job IDs (up to 50)
- Responsive design with gradient background
