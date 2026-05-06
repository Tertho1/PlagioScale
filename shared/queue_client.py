"""
Redis queue client for job management.
"""
import redis
import json
from typing import Optional, List
from shared.models import Job, JobStatus
import os


class QueueClient:
    """Redis-backed queue for job management."""
    
    def __init__(self, host: str = None, port: int = None):
        """Initialize Redis connection."""
        self.host = host or os.getenv('REDIS_HOST', 'redis')
        self.port = port or int(os.getenv('REDIS_PORT', 6379))
        self.redis_client = redis.Redis(
            host=self.host,
            port=self.port,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True
        )
        # Ensure connection
        try:
            self.redis_client.ping()
        except Exception as e:
            print(f"⚠ Redis not available: {e}")
    
    def enqueue_job(self, job: Job) -> bool:
        """Push job to queue."""
        try:
            self.redis_client.lpush('job_queue', job.to_json())
            # Store job metadata for status checks
            self.redis_client.hset(f'job:{job.job_id}', mapping={'status': job.status.value})
            print(f"[Queue] Job {job.job_id} enqueued")
            return True
        except Exception as e:
            print(f"[Queue Error] Failed to enqueue: {e}")
            return False
    
    def dequeue_job(self, timeout: int = 5) -> Optional[Job]:
        """Pop job from queue (blocking)."""
        try:
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
            return self.redis_client.llen('job_queue')
        except:
            return 0
    
    def update_job_status(self, job_id: str, status: JobStatus) -> bool:
        """Update job status in metadata store."""
        try:
            self.redis_client.hset(f'job:{job_id}', 'status', status.value)
            return True
        except Exception as e:
            print(f"[Queue Error] Failed to update status: {e}")
            return False
    
    def get_job_status(self, job_id: str) -> Optional[str]:
        """Retrieve job status."""
        try:
            status = self.redis_client.hget(f'job:{job_id}', 'status')
            return status
        except:
            return None
    
    def store_result(self, job_id: str, result: dict) -> bool:
        """Store job result."""
        try:
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
            data = self.redis_client.hgetall(f'job:{job_id}')
            if data and 'result' in data:
                return json.loads(data['result'])
        except:
            pass
        return None
    
    def get_job_full_data(self, job_id: str) -> Optional[dict]:
        """Get complete job metadata."""
        try:
            return self.redis_client.hgetall(f'job:{job_id}')
        except:
            return None
