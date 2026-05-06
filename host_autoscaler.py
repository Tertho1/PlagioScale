#!/usr/bin/env python3
"""
Host-side queue autoscaler for PlagioScale.

Why this exists:
- The in-container autoscaler can read Redis, but in this Windows/Docker setup it may
  fail to talk to the Docker daemon from inside the container.
- Running the scaler on the host avoids that limitation while still demonstrating
  real elasticity: queue depth increases, worker replicas increase, then scale back down.

Default behavior:
- Poll Redis queue depth every 5 seconds.
- Scale up to 3 workers when queue depth exceeds 10.
- Scale back to 1 worker when queue depth drops below 3.

Usage:
    python host_autoscaler.py

Optional env vars:
    SCALE_UP_THRESHOLD=8
    SCALE_DOWN_THRESHOLD=3
    MIN_WORKERS=1
    MAX_WORKERS=5
    COOLDOWN_SECONDS=10
    POLL_INTERVAL=2
    DOCKER_COMPOSE_CMD=docker compose
    REDIS_SERVICE_NAME=redis
    WORKER_SERVICE_NAME=worker
    AUTOSCALER_EVENTS_KEY=autoscaler_events
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AutoscalerConfig:
    scale_up_threshold: int = int(os.getenv("SCALE_UP_THRESHOLD", "10"))
    scale_down_threshold: int = int(os.getenv("SCALE_DOWN_THRESHOLD", "3"))
    min_workers: int = int(os.getenv("MIN_WORKERS", "1"))
    max_workers: int = int(os.getenv("MAX_WORKERS", "5"))
    cooldown_seconds: int = int(os.getenv("COOLDOWN_SECONDS", "20"))
    poll_interval: int = int(os.getenv("POLL_INTERVAL", "5"))
    docker_compose_cmd: str = os.getenv("DOCKER_COMPOSE_CMD", "docker compose")
    redis_service_name: str = os.getenv("REDIS_SERVICE_NAME", "redis")
    worker_service_name: str = os.getenv("WORKER_SERVICE_NAME", "worker")
    events_key: str = os.getenv("AUTOSCALER_EVENTS_KEY", "autoscaler_events")


class HostQueueAutoscaler:
    def __init__(self, config: AutoscalerConfig | None = None):
        self.config = config or AutoscalerConfig()
        self.last_scale_time = 0.0
        self.current_workers = self.config.min_workers

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [HostAutoscaler] {message}", flush=True)

    def _run(self, command: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, check=check)

    def _compose_args(self) -> list[str]:
        return self.config.docker_compose_cmd.split()

    def get_queue_length(self) -> int:
        command = self._compose_args() + ["exec", "-T", self.config.redis_service_name, "redis-cli", "LLEN", "job_queue"]
        result = self._run(command)
        if result.returncode != 0:
            self.log(f"⚠ Queue read failed: {result.stderr.strip() or result.stdout.strip()}")
            return 0

        value = result.stdout.strip()
        try:
            return int(value)
        except ValueError:
            return 0

    def get_current_workers(self) -> int:
        command = [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.service=worker",
            "--filter",
            "label=com.docker.compose.project=plagioscale",
            "--format",
            "{{.Names}}",
        ]
        result = self._run(command)
        if result.returncode != 0:
            self.log(f"⚠ Worker count read failed: {result.stderr.strip() or result.stdout.strip()}")
            return self.current_workers

        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        count = len(names)
        if count:
            self.current_workers = count
        return count or self.current_workers

    def publish_event(self, level: str, message: str, queue_length: int, workers: int) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            "queue_length": queue_length,
            "workers": workers,
        }
        payload = json.dumps(event)
        command = self._compose_args() + ["exec", "-T", self.config.redis_service_name, "redis-cli", "LPUSH", self.config.events_key, payload]
        self._run(command)
        trim_command = self._compose_args() + ["exec", "-T", self.config.redis_service_name, "redis-cli", "LTRIM", self.config.events_key, "0", "99"]
        self._run(trim_command)

    def scale_workers(self, target_workers: int) -> bool:
        if target_workers == self.current_workers:
            return True

        self.log(f"--- [CLOUD ACTION] Scaling {self.config.worker_service_name} to {target_workers} instances... ---")
        command = self._compose_args() + ["up", "-d", "--scale", f"{self.config.worker_service_name}={target_workers}"]
        result = self._run(command)
        if result.returncode != 0:
            self.log(f"✗ Scale command failed: {result.stderr.strip() or result.stdout.strip()}")
            self.publish_event("error", f"Scale to {target_workers} failed", self.get_queue_length(), self.current_workers)
            return False

        self.current_workers = target_workers
        self.last_scale_time = time.time()
        self.publish_event("info", f"Scaled workers to {target_workers}", self.get_queue_length(), target_workers)
        return True

    def can_scale_now(self) -> bool:
        return (time.time() - self.last_scale_time) >= self.config.cooldown_seconds

    def decide_target(self, queue_length: int, current_workers: int) -> int:
        if queue_length > self.config.scale_up_threshold:
            return min(current_workers + 1, self.config.max_workers)
        if queue_length < self.config.scale_down_threshold:
            return max(current_workers - 1, self.config.min_workers)
        return current_workers

    def run(self) -> None:
        self.log(
            f"PlagioScale Cloud Monitor Active (queue-based, up>{self.config.scale_up_threshold}, down<{self.config.scale_down_threshold})"
        )
        self.log(f"Using: {self.config.docker_compose_cmd} | Redis service: {self.config.redis_service_name} | Worker service: {self.config.worker_service_name}")

        self._tick(once=False)

    def _tick(self, once: bool = False) -> None:
        while True:
            queue_length = self.get_queue_length()
            current_workers = self.get_current_workers()
            self.log(f"Queue depth: {queue_length} | Workers: {current_workers}/{self.config.max_workers}")
            self.publish_event("debug", "Tick", queue_length, current_workers)

            if self.can_scale_now():
                target_workers = self.decide_target(queue_length, current_workers)
                if target_workers != current_workers:
                    if queue_length > self.config.scale_up_threshold:
                        self.log("!!! HIGH LOAD DETECTED !!!")
                    elif queue_length < self.config.scale_down_threshold:
                        self.log("--- LOW LOAD DETECTED ---")
                    self.scale_workers(target_workers)
            else:
                remaining = max(0, int(self.config.cooldown_seconds - (time.time() - self.last_scale_time)))
                self.log(f"⏳ Cooldown active ({remaining}s remaining)")

            if once:
                return

            time.sleep(self.config.poll_interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Host-side queue autoscaler for PlagioScale")
    parser.add_argument("--once", action="store_true", help="Run one tick and exit")
    args = parser.parse_args()

    try:
        autoscaler = HostQueueAutoscaler()
        if args.once:
            autoscaler._tick(once=True)
        else:
            autoscaler.run()
    except KeyboardInterrupt:
        print("Shutting down host autoscaler", flush=True)
        return 130
    except FileNotFoundError as exc:
        print(f"Missing command: {exc}", flush=True)
        return 1
    except Exception as exc:
        print(f"Fatal autoscaler error: {exc}", flush=True)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
