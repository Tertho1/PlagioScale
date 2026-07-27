"""
Redis queue client for job management.
"""
import json
import os
import time
import asyncio
from typing import Optional

import redis
from redis import asyncio as aioredis

from shared.models import Job, JobStatus

_RECONNECT_BASE = 1
_RECONNECT_MAX = 30
_RECONNECT_MULT = 2
_REDIS_TTL = 86400 * 7


class QueueClient:
    """Redis-backed queue for job management."""

    def __init__(self, host: str = None, port: int = None):
        """Initialize Redis connection."""
        self.host = host or os.getenv('REDIS_HOST', 'redis')
        self.port = port or int(os.getenv('REDIS_PORT', 6379))
        self.password = os.getenv('REDIS_PASSWORD', None)
        self._connect()

    def _connect(self):
        self.redis_client = redis.Redis(
            host=self.host,
            port=self.port,
            password=self.password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
            socket_keepalive=True,
            retry_on_timeout=True,
        )

    def _ensure_connection(self):
        """Check connection is alive; reconnect with exponential backoff if dead."""
        delay = _RECONNECT_BASE
        while True:
            try:
                self.redis_client.ping()
                return
            except (redis.ConnectionError, redis.TimeoutError, OSError):
                print(f"[Queue] Redis connection lost, reconnecting in {delay}s...")
                time.sleep(delay)
                try:
                    self._connect()
                    self.redis_client.ping()
                    print("[Queue] Redis reconnected")
                    return
                except (redis.ConnectionError, redis.TimeoutError, OSError):
                    delay = min(delay * _RECONNECT_MULT, _RECONNECT_MAX)

    def enqueue_job(self, job: Job) -> bool:
        """Push job to queue."""
        try:
            self._ensure_connection()
            self.redis_client.lpush('job_queue', job.to_json())
            self.redis_client.hset(f'job:{job.job_id}', mapping={'status': job.status.value})
            self.redis_client.expire(f'job:{job.job_id}', _REDIS_TTL)
            print(f"[Queue] Job {job.job_id} enqueued")
            return True
        except Exception as e:
            print(f"[Queue Error] Failed to enqueue: {e}")
            return False

    def dequeue_job(self, timeout: int = 5) -> Optional[Job]:
        """Pop job from queue (blocking)."""
        try:
            self._ensure_connection()
            result = self.redis_client.brpop('job_queue', timeout=timeout)
            if result:
                job_json = result[1]
                return Job.from_json(job_json)
        except Exception as e:
            print(f"[Queue Error] Failed to dequeue: {e}")
        return None

    def get_queue_length(self) -> int:
        """Get current queue size."""
        try:
            self._ensure_connection()
            return self.redis_client.llen('job_queue')
        except Exception as e:
            print(f"[Queue Error] Failed to get queue length: {e}")
            return 0

    def update_job_status(self, job_id: str, status: JobStatus) -> bool:
        """Update job status in metadata store."""
        try:
            self._ensure_connection()
            self.redis_client.hset(f'job:{job_id}', 'status', status.value)
            return True
        except Exception as e:
            print(f"[Queue Error] Failed to update status: {e}")
            return False

    def get_job_status(self, job_id: str) -> Optional[str]:
        """Retrieve job status."""
        try:
            self._ensure_connection()
            status = self.redis_client.hget(f'job:{job_id}', 'status')
            return status
        except Exception as e:
            print(f"[Queue Error] Failed to get job status: {e}")
            return None

    def store_result(self, job_id: str, result: dict) -> bool:
        """Store job result."""
        try:
            self._ensure_connection()
            self.redis_client.hset(f'job:{job_id}', mapping={
                'result': json.dumps(result),
                'status': JobStatus.COMPLETED.value
            })
            return True
        except Exception as e:
            print(f"[Queue Error] Failed to store result: {e}")
            return False

    def get_result(self, job_id: str) -> Optional[dict]:
        """Retrieve job result."""
        try:
            self._ensure_connection()
            data = self.redis_client.hgetall(f'job:{job_id}')
            if data and 'result' in data:
                return json.loads(data['result'])
        except Exception as e:
            print(f"[Queue Error] Failed to get result: {e}")
        return None

    def get_job_full_data(self, job_id: str) -> Optional[dict]:
        """Get complete job metadata."""
        try:
            self._ensure_connection()
            return self.redis_client.hgetall(f'job:{job_id}')
        except Exception as e:
            print(f"[Queue Error] Failed to get full job data: {e}")
            return None


class AsyncQueueClient:
    """Async Redis-backed queue for job management (used by FastAPI)."""

    def __init__(self, host: str = None, port: int = None):
        self.host = host or os.getenv('REDIS_HOST', 'redis')
        self.port = port or int(os.getenv('REDIS_PORT', 6379))
        self.password = os.getenv('REDIS_PASSWORD', None)
        self._redis: Optional[aioredis.Redis] = None

    async def _connect(self):
        self._redis = aioredis.Redis(
            host=self.host,
            port=self.port,
            password=self.password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
            socket_keepalive=True,
            retry_on_timeout=True,
        )

    async def connect(self):
        if self._redis is None:
            await self._connect()

    async def _ensure_connection(self):
        """Check connection is alive; reconnect with exponential backoff if dead."""
        delay = _RECONNECT_BASE
        while True:
            if self._redis is None:
                await self._connect()
            try:
                await self._redis.ping()
                return
            except (redis.ConnectionError, redis.TimeoutError, OSError, AttributeError):
                print(f"[AsyncQueue] Redis connection lost, reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                try:
                    await self._connect()
                    await self._redis.ping()
                    print("[AsyncQueue] Redis reconnected")
                    return
                except (redis.ConnectionError, redis.TimeoutError, OSError):
                    delay = min(delay * _RECONNECT_MULT, _RECONNECT_MAX)

    async def enqueue_job(self, job: Job) -> bool:
        try:
            await self._ensure_connection()
            await self._redis.lpush('job_queue', job.to_json())
            await self._redis.hset(f'job:{job.job_id}', mapping={'status': job.status.value})
            await self._redis.expire(f'job:{job.job_id}', _REDIS_TTL)
            print(f"[AsyncQueue] Job {job.job_id} enqueued")
            return True
        except Exception as e:
            print(f"[AsyncQueue Error] Failed to enqueue: {e}")
            return False

    async def get_queue_length(self) -> int:
        try:
            await self._ensure_connection()
            return await self._redis.llen('job_queue')
        except Exception as e:
            print(f"[AsyncQueue Error] Failed to get queue length: {e}")
            return 0

    async def get_job_status(self, job_id: str) -> Optional[str]:
        try:
            await self._ensure_connection()
            return await self._redis.hget(f'job:{job_id}', 'status')
        except Exception as e:
            print(f"[AsyncQueue Error] Failed to get job status: {e}")
            return None

    async def get_result(self, job_id: str) -> Optional[dict]:
        try:
            await self._ensure_connection()
            data = await self._redis.hgetall(f'job:{job_id}')
            if data and 'result' in data:
                return json.loads(data['result'])
        except Exception as e:
            print(f"[AsyncQueue Error] Failed to get result: {e}")
        return None

    async def update_job_status(self, job_id: str, status: JobStatus) -> bool:
        try:
            await self._ensure_connection()
            await self._redis.hset(f'job:{job_id}', 'status', status.value)
            return True
        except Exception as e:
            print(f"[AsyncQueue Error] Failed to update status: {e}")
            return False

    async def store_result(self, job_id: str, result: dict) -> bool:
        try:
            await self._ensure_connection()
            await self._redis.hset(f'job:{job_id}', mapping={
                'result': json.dumps(result),
                'status': JobStatus.COMPLETED.value
            })
            return True
        except Exception as e:
            print(f"[AsyncQueue Error] Failed to store result: {e}")
            return False
