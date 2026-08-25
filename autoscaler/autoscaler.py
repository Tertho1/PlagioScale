"""
PlagioScale Autoscaler — scales workers (queue-based) and API replicas (latency-based).
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

import docker
import redis
from prometheus_client import Counter, Gauge, start_http_server


class Autoscaler:
    """Scales workers by queue depth and API replicas by p95 latency."""

    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.project_name = os.getenv("COMPOSE_PROJECT_NAME", "plagioscale")

        # Worker scaling (queue-based)
        self.scale_up_threshold = int(os.getenv("SCALE_UP_THRESHOLD", 10))
        self.scale_down_threshold = int(os.getenv("SCALE_DOWN_THRESHOLD", 3))
        self.min_workers = int(os.getenv("MIN_WORKERS", 1))
        self.max_workers = int(os.getenv("MAX_WORKERS", 5))

        # API scaling (latency-based)
        self.api_scale_up_ms = float(os.getenv("API_SCALE_UP_MS", 500))
        self.api_scale_down_ms = float(os.getenv("API_SCALE_DOWN_MS", 200))
        self.min_api = int(os.getenv("MIN_API", 1))
        self.max_api = int(os.getenv("MAX_API", 5))
        self.api_cooldown = int(os.getenv("API_COOLDOWN_SECONDS", 60))

        # Shared
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", 60))
        self.poll_interval = int(os.getenv("POLL_INTERVAL", 5))
        self.events_key = os.getenv("AUTOSCALER_EVENTS_KEY", "autoscaler_events")

        # Redis
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host, port=self.redis_port,
                decode_responses=True, socket_connect_timeout=5,
            )
            self.redis_client.ping()
            self.log("✓ Connected to Redis")
        except Exception as e:
            self.log(f"✗ Redis failed: {e}")
            self.redis_client = None

        # Docker
        try:
            self.docker_client = docker.from_env()
            self.docker_client.ping()
            self.log("✓ Connected to Docker daemon")
        except Exception as e:
            self.log(f"✗ Docker failed: {e}")
            self.docker_client = None

        # Tracking
        self.last_worker_scale = 0
        self.last_api_scale = 0
        self.current_worker_count = self.min_workers

        # Prometheus
        self.P_WORKERS = Gauge("plagioscale_workers", "Worker containers")
        self.P_API = Gauge("plagioscale_api_replicas", "API replicas")
        self.P_QUEUE = Gauge("plagioscale_queue_length", "Job queue length")
        self.P_API_P95 = Gauge("plagioscale_api_p95_ms", "API p95 latency ms")
        self.P_SCALE_EVENTS = Counter("plagioscale_scale_events_total", "Scale events")

        try:
            start_http_server(8002)
            self.log("✓ Prometheus metrics on :8002")
        except Exception as e:
            self.log(f"⚠ Prometheus failed: {e}")

        self.log(f"Config: workers({self.min_workers}-{self.max_workers}, "
                 f"up>{self.scale_up_threshold}, down<{self.scale_down_threshold}) "
                 f"api({self.min_api}-{self.max_api}, "
                 f"up>{self.api_scale_up_ms}ms, down<{self.api_scale_down_ms}ms)")

    def log(self, msg):
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [Autoscaler] {msg}", flush=True)

    def publish_event(self, level, message, **extra):
        if not self.redis_client:
            return
        try:
            event = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": level, "message": message, **extra}
            self.redis_client.lpush(self.events_key, json.dumps(event))
            self.redis_client.ltrim(self.events_key, 0, 99)
        except Exception:
            pass

    # ── Queue ───────────────────────────────────────────────────────────────
    def get_queue_length(self):
        if not self.redis_client:
            return 0
        try:
            return self.redis_client.llen("job_queue")
        except Exception:
            return 0

    # ── Worker scaling ──────────────────────────────────────────────────────
    def get_current_workers(self):
        if not self.docker_client:
            return self.current_worker_count
        try:
            containers = self.docker_client.containers.list(
                filters={"label": "com.docker.compose.service=worker"}
            )
            count = len([c for c in containers if c.status == "running"])
            self.current_worker_count = count
            return count
        except Exception:
            return self.current_worker_count

    def scale_workers(self, target):
        if target == self.current_worker_count:
            return True
        if not self.docker_client:
            return False

        self.log(f"↻ Workers: {self.current_worker_count} → {target}")
        try:
            containers = self.docker_client.containers.list(
                filters={"label": "com.docker.compose.service=worker"}, all=True
            )
            running = [c for c in containers if c.status == "running"]

            if target > len(running):
                diff = target - len(running)
                if containers:
                    tmpl = containers[0]
                    image_ref = tmpl.attrs["Config"]["Image"]
                    env = tmpl.attrs["Config"]["Env"]
                    networks = tmpl.attrs["NetworkSettings"]["Networks"]
                    net_name = list(networks.keys())[0] if networks else None
                    mounts = tmpl.attrs["Mounts"]

                    for i in range(diff):
                        num = len(running) + i + 1
                        env_dict = dict(e.split("=", 1) for e in env if "=" in e)
                        env_dict["WORKER_ID"] = f"worker-{num}"
                        vols = {}
                        for m in mounts:
                            if m["Type"] == "bind":
                                vols[m["Source"]] = {"bind": m["Destination"], "mode": "rw"}
                            elif m["Type"] == "volume":
                                vols[m["Name"]] = {"bind": m["Destination"], "mode": "rw"}
                        try:
                            self.docker_client.containers.run(
                                image_ref,
                                name=f"{self.project_name}-worker-{num}",
                                environment=env_dict,
                                restart_policy={"Name": "unless-stopped"},
                                detach=True,
                                labels={"com.docker.compose.project": self.project_name, "com.docker.compose.service": "worker"},
                                network=net_name,
                                volumes=vols or None,
                                mem_limit="512m", memswap_limit="512m",
                            )
                            self.log(f"  ✓ Started worker-{num}")
                        except Exception as e:
                            self.log(f"  ✗ worker-{num}: {e}")

            elif target < len(running):
                diff = len(running) - target
                by_age = sorted(running, key=lambda c: c.attrs["State"]["StartedAt"], reverse=True)
                for c in by_age[:diff]:
                    try:
                        c.stop(timeout=10)
                        c.remove()
                        self.log(f"  ✓ Stopped {c.name}")
                    except Exception as e:
                        self.log(f"  ⚠ {c.name}: {e}")

            self.current_worker_count = target
            self.last_worker_scale = time.time()
            self.log(f"✓ Workers now: {target}")
            self.publish_event("info", f"Scaled workers to {target}", workers=target)
            try:
                self.P_SCALE_EVENTS.inc()
                self.P_WORKERS.set(target)
            except Exception:
                pass
            return True
        except Exception as e:
            self.log(f"✗ Worker scale error: {e}")
            return False

    # ── API scaling ─────────────────────────────────────────────────────────
    def get_current_api_count(self):
        if not self.docker_client:
            return self.min_api
        try:
            containers = self.docker_client.containers.list(
                filters={"label": "com.docker.compose.service=api-service"}
            )
            count = len([c for c in containers if c.status == "running"])
            return max(count, self.min_api)
        except Exception:
            return self.min_api

    def get_api_p95(self):
        """Query p95 latency from a random running API replica."""
        if not self.docker_client:
            return 0
        try:
            containers = self.docker_client.containers.list(
                filters={"label": "com.docker.compose.service=api-service"}
            )
            running = [c for c in containers if c.status == "running"]
            if not running:
                return 0
            # Try each container's IP on the internal network
            for c in running:
                networks = c.attrs["NetworkSettings"]["Networks"]
                for net_name, net_info in networks.items():
                    ip = net_info.get("IPAddress")
                    if ip:
                        try:
                            url = f"http://{ip}:8000/metrics"
                            req = urllib.request.urlopen(url, timeout=3)
                            data = json.loads(req.read())
                            p95 = data.get("p95_ms", 0)
                            try:
                                self.P_API_P95.set(p95)
                            except Exception:
                                pass
                            return p95
                        except Exception:
                            continue
            return 0
        except Exception:
            return 0

    def scale_api(self, target):
        if target == self.get_current_api_count():
            return True
        if not self.docker_client:
            return False

        current = self.get_current_api_count()
        self.log(f"↻ API replicas: {current} → {target}")

        try:
            containers = self.docker_client.containers.list(
                filters={"label": "com.docker.compose.service=api-service"}, all=True
            )
            running = [c for c in containers if c.status == "running"]

            if target > len(running):
                diff = target - len(running)
                if containers:
                    tmpl = containers[0]
                    image_ref = tmpl.attrs["Config"]["Image"]
                    env = tmpl.attrs["Config"]["Env"]
                    networks = tmpl.attrs["Config"]["NetworkSettings"]["Networks"]
                    net_name = list(networks.keys())[0] if networks else None
                    mounts = tmpl.attrs["Mounts"]

                    for i in range(diff):
                        num = len(running) + i + 1
                        env_dict = dict(e.split("=", 1) for e in env if "=" in e)
                        # Remove host port bindings (not needed for internal replicas)
                        vols = {}
                        for m in mounts:
                            if m["Type"] == "bind":
                                vols[m["Source"]] = {"bind": m["Destination"], "mode": "rw"}
                            elif m["Type"] == "volume":
                                vols[m["Name"]] = {"bind": m["Destination"], "mode": "rw"}
                        try:
                            self.docker_client.containers.run(
                                image_ref,
                                name=f"{self.project_name}-api-{num}",
                                environment=env_dict,
                                restart_policy={"Name": "unless-stopped"},
                                detach=True,
                                labels={
                                    "com.docker.compose.project": self.project_name,
                                    "com.docker.compose.service": "api-service",
                                },
                                network=net_name,
                                volumes=vols or None,
                                mem_limit="384m", memswap_limit="384m",
                            )
                            self.log(f"  ✓ Started api-{num}")
                        except Exception as e:
                            self.log(f"  ✗ api-{num}: {e}")

            elif target < len(running):
                diff = len(running) - target
                by_age = sorted(running, key=lambda c: c.attrs["State"]["StartedAt"], reverse=True)
                for c in by_age[:diff]:
                    try:
                        c.stop(timeout=10)
                        c.remove()
                        self.log(f"  ✓ Stopped {c.name}")
                    except Exception as e:
                        self.log(f"  ⚠ {c.name}: {e}")

            self.last_api_scale = time.time()
            new_count = self.get_current_api_count()
            self.log(f"✓ API replicas now: {new_count}")
            self.publish_event("info", f"Scaled API to {new_count} replicas", api_replicas=new_count)
            try:
                self.P_SCALE_EVENTS.inc()
                self.P_API.set(new_count)
            except Exception:
                pass
            return True
        except Exception as e:
            self.log(f"✗ API scale error: {e}")
            return False

    # ── Decision logic ──────────────────────────────────────────────────────
    def tick(self):
        queue_length = self.get_queue_length()
        workers = self.get_current_workers()
        api_count = self.get_current_api_count()
        p95 = self.get_api_p95()

        self.log(f"Queue: {queue_length} | Workers: {workers}/{self.max_workers} | API: {api_count}/{self.max_api} | p95: {p95:.0f}ms")
        self.publish_event("debug", "Tick", queue_length=queue_length, workers=workers, api_replicas=api_count)

        try:
            self.P_WORKERS.set(workers)
            self.P_API.set(api_count)
            self.P_QUEUE.set(queue_length)
        except Exception:
            pass

        now = time.time()

        # Worker scaling (queue-based)
        if (now - self.last_worker_scale) >= self.cooldown_seconds:
            if queue_length > self.scale_up_threshold and workers < self.max_workers:
                self.scale_workers(min(workers + 1, self.max_workers))
            elif queue_length < self.scale_down_threshold and workers > self.min_workers:
                self.scale_workers(max(workers - 1, self.min_workers))

        # API scaling (latency-based)
        if (now - self.last_api_scale) >= self.api_cooldown:
            if p95 > self.api_scale_up_ms and api_count < self.max_api:
                self.scale_api(min(api_count + 1, self.max_api))
            elif p95 < self.api_scale_down_ms and p95 > 0 and api_count > self.min_api:
                self.scale_api(max(api_count - 1, self.min_api))

    def run(self):
        self.log("Starting autoscaler")
        try:
            while True:
                self.tick()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            self.log("Shutting down")
        except Exception as e:
            self.log(f"Fatal: {e}")
            raise


if __name__ == "__main__":
    Autoscaler().run()
