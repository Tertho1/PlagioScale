import json
import os
from datetime import datetime

import docker
import redis
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from prometheus_client import make_asgi_app, Gauge


app = FastAPI(title="PlagioScale Monitoring", version="1.0.0")

# Prometheus metrics
P_QUEUE = Gauge('plagioscale_monitor_queue_length', 'Queue length observed by monitoring service')
P_WORKERS = Gauge('plagioscale_monitor_workers', 'Worker count observed by monitoring service')

# Mount Prometheus metrics endpoint
app.mount('/metrics', make_asgi_app())

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
COMPOSE_PROJECT_NAME = os.getenv("COMPOSE_PROJECT_NAME", "plagioscale")
EVENTS_KEY = os.getenv("AUTOSCALER_EVENTS_KEY", "autoscaler_events")


def get_redis_client():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def get_docker_client():
    return docker.from_env()


@app.get("/health")
def health():
    return {"status": "healthy", "service": "monitoring-service"}


@app.get("/api/overview")
def overview():
    now = datetime.utcnow().isoformat()
    queue_length = 0
    workers = 0
    completed = 0
    processing = 0
    failed = 0

    try:
        r = get_redis_client()
        queue_length = r.llen("job_queue")
        for key in r.scan_iter("job:*"):
            status = r.hget(key, "status")
            if status == "COMPLETED":
                completed += 1
            elif status == "PROCESSING":
                processing += 1
            elif status == "FAILED":
                failed += 1
    except Exception:
        pass

    try:
        d = get_docker_client()
        containers = d.containers.list(filters={"label": "com.docker.compose.service=worker"})
        if not containers:
            containers = d.containers.list(filters={"name": f"{COMPOSE_PROJECT_NAME}-worker"})
        workers = len([c for c in containers if c.status == "running"])
    except Exception:
        pass

    if workers == 0:
      try:
        r = get_redis_client()
        raw = r.lindex(EVENTS_KEY, 0)
        if raw:
          latest = json.loads(raw)
          workers = int(latest.get("workers", 0))
      except Exception:
        pass

    try:
      P_QUEUE.set(queue_length)
      P_WORKERS.set(workers)
    except Exception:
      pass

    return {
      "timestamp": now,
      "queue_length": queue_length,
      "workers": workers,
      "jobs": {
        "completed": completed,
        "processing": processing,
        "failed": failed,
      },
    }


@app.get("/api/events")
def events(limit: int = 20):
    rows = []
    try:
        r = get_redis_client()
        raw = r.lrange(EVENTS_KEY, 0, max(0, limit - 1))
        for item in raw:
            try:
                rows.append(json.loads(item))
            except Exception:
                continue
    except Exception:
        pass
    return {"events": rows}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>PlagioScale Live Dashboard</title>
    <style>
      :root {
        --bg: #f4f6fb;
        --card: #ffffff;
        --ink: #13233a;
        --muted: #5e6b80;
      }
      body {
        margin: 0;
        font-family: Segoe UI, Tahoma, Geneva, Verdana, sans-serif;
        background: radial-gradient(circle at top right, #dde9ff 0%, var(--bg) 55%);
        color: var(--ink);
      }
      .wrap { max-width: 980px; margin: 0 auto; padding: 24px; }
      h1 { margin: 0 0 8px 0; font-size: 28px; }
      .sub { color: var(--muted); margin-bottom: 20px; }
      .grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
      .card { background: var(--card); border-radius: 14px; box-shadow: 0 12px 24px rgba(15,35,65,0.08); padding: 16px; }
      .label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }
      .value { font-size: 36px; font-weight: 700; margin-top: 8px; }
      .events { margin-top: 18px; }
      .events h2 { margin: 0 0 10px 0; font-size: 18px; }
      #eventsList {
        background: #0c1626;
        color: #e8f0ff;
        border-radius: 12px;
        padding: 12px;
        min-height: 220px;
        max-height: 420px;
        overflow: auto;
        font-family: Consolas, Courier New, monospace;
        font-size: 12px;
      }
      .line { margin: 0 0 8px 0; }
      .footer { margin-top: 14px; color: var(--muted); font-size: 12px; }
    </style>
  </head>
  <body>
    <div class=\"wrap\">
      <h1>PlagioScale Live Dashboard</h1>
      <div class=\"sub\">Queue depth, worker count, and autoscaler decisions in real time.</div>
      <div class=\"grid\">
        <div class=\"card\"><div class=\"label\">Queue Length</div><div id=\"queue\" class=\"value\">0</div></div>
        <div class=\"card\"><div class=\"label\">Workers Running</div><div id=\"workers\" class=\"value\">0</div></div>
        <div class=\"card\"><div class=\"label\">Completed Jobs</div><div id=\"completed\" class=\"value\">0</div></div>
        <div class=\"card\"><div class=\"label\">Processing Jobs</div><div id=\"processing\" class=\"value\">0</div></div>
      </div>
      <div class=\"events\">
        <h2>Autoscaler Events</h2>
        <div id=\"eventsList\"></div>
      </div>
      <div class=\"footer\" id=\"ts\">Last update: --</div>
    </div>

    <script>
      function cssLevel(level) {
        const l = (level || 'info').toLowerCase();
        if (l === 'error') return 'color:#ff8a8a';
        if (l === 'warn') return 'color:#ffcf72';
        if (l === 'debug') return 'color:#a4b6d1';
        return 'color:#7dc9ff';
      }

      async function refresh() {
        try {
          const [overviewRes, eventsRes] = await Promise.all([
            fetch('/api/overview'),
            fetch('/api/events?limit=25')
          ]);

          const overview = await overviewRes.json();
          const events = await eventsRes.json();

          document.getElementById('queue').textContent = overview.queue_length;
          document.getElementById('workers').textContent = overview.workers;
          document.getElementById('completed').textContent = overview.jobs.completed;
          document.getElementById('processing').textContent = overview.jobs.processing;
          document.getElementById('ts').textContent = 'Last update: ' + new Date().toLocaleTimeString();

          const list = document.getElementById('eventsList');
          list.innerHTML = '';
          (events.events || []).forEach((evt) => {
            const p = document.createElement('p');
            p.className = 'line';
            p.style = cssLevel(evt.level);
            p.textContent = '[' + (evt.timestamp || '') + '] [' + ((evt.level || 'info').toUpperCase()) + '] '
              + (evt.message || '') + ' | queue=' + (evt.queue_length ?? '-') + ' workers=' + (evt.workers ?? '-');
            list.appendChild(p);
          });
        } catch (e) {
          // Keep refreshing even if one poll fails.
        }
      }

      refresh();
      setInterval(refresh, 2000);
    </script>
  </body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8090)
