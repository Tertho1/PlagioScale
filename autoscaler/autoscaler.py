"""
PlagioScale Autoscaler - monitors queue length and scales workers automatically.
Uses queue depth (not CPU) to make scaling decisions.
"""
import redis
import docker
import time
import os
import json
from datetime import datetime
from prometheus_client import start_http_server, Gauge, Counter


class QueueBasedAutoscaler:
    """Autoscaler that watches Redis queue and scales Docker Compose workers."""
    
    def __init__(self):
        """Initialize autoscaler with Redis and Docker clients."""
        self.redis_host = os.getenv('REDIS_HOST', 'redis')
        self.redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.project_name = os.getenv('COMPOSE_PROJECT_NAME', 'plagioscale')
        
        # Scaling parameters
        self.scale_up_threshold = int(os.getenv('SCALE_UP_THRESHOLD', 10))
        self.scale_down_threshold = int(os.getenv('SCALE_DOWN_THRESHOLD', 3))
        self.min_workers = int(os.getenv('MIN_WORKERS', 1))
        self.max_workers = int(os.getenv('MAX_WORKERS', 5))
        self.cooldown_seconds = int(os.getenv('COOLDOWN_SECONDS', 60))
        self.poll_interval = int(os.getenv('POLL_INTERVAL', 5))
        
        # Event stream key for dashboard
        self.events_key = os.getenv('AUTOSCALER_EVENTS_KEY', 'autoscaler_events')

        # Connect to Redis
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True,
                socket_connect_timeout=5
            )
            self.redis_client.ping()
            self.log("✓ Connected to Redis")
        except Exception as e:
            self.log(f"✗ Redis connection failed: {e}")
            self.redis_client = None
        
        # Connect to Docker
        try:
            self.docker_client = docker.from_env()
            self.docker_client.ping()
            self.log("✓ Connected to Docker daemon")
        except Exception as e:
            self.log(f"✗ Docker connection failed: {e}")
            self.docker_client = None
        
        # Tracking
        self.last_scale_time = 0
        self.current_worker_count = self.min_workers
        
        self.log(f"Configuration: scale_up_threshold={self.scale_up_threshold}, "
                f"scale_down_threshold={self.scale_down_threshold}, "
                f"min_workers={self.min_workers}, max_workers={self.max_workers}, "
                f"cooldown={self.cooldown_seconds}s")

        # Prometheus metrics
        self.P_QUEUE_LENGTH = Gauge('plagioscale_autoscaler_queue_length', 'Queue length observed by autoscaler')
        self.P_WORKERS = Gauge('plagioscale_autoscaler_workers', 'Number of worker containers')
        self.P_SCALE_EVENTS = Counter('plagioscale_autoscaler_scale_events_total', 'Scale events performed')

        # Start Prometheus metrics server
        try:
            start_http_server(8002)
            self.log('✓ Prometheus metrics server started on :8002')
        except Exception as e:
            self.log(f'⚠ Prometheus metrics server failed to start: {e}')
    
    def log(self, message: str):
        """Log with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [Autoscaler] {message}", flush=True)

    def publish_event(self, level: str, message: str, queue_length: int = -1, workers: int = -1):
        """Publish an autoscaler event to Redis for dashboard consumption."""
        if not self.redis_client:
            return
        try:
            event = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': message,
                'queue_length': queue_length,
                'workers': workers,
            }
            self.redis_client.lpush(self.events_key, json.dumps(event))
            self.redis_client.ltrim(self.events_key, 0, 99)
        except Exception:
            # Event publishing should never crash autoscaling loop
            pass
        try:
            if queue_length >= 0:
                self.P_QUEUE_LENGTH.set(queue_length)
            if workers >= 0:
                self.P_WORKERS.set(workers)
        except Exception:
            pass
    
    def get_queue_length(self) -> int:
        """Get current length of job queue."""
        if not self.redis_client:
            return 0
        try:
            return self.redis_client.llen('job_queue')
        except Exception as e:
            self.log(f"⚠ Error reading queue length: {e}")
            return 0
    
    def get_current_workers(self) -> int:
        """Get number of currently running worker containers."""
        if not self.docker_client:
            return self.current_worker_count
        
        try:
            containers = self.docker_client.containers.list(
                filters={'label': 'com.docker.compose.service=worker'}
            )
            if not containers:
                containers = self.docker_client.containers.list(
                    filters={'name': f'{self.project_name}-worker'}
                )
            # Filter for running worker-* containers
            worker_count = len([c for c in containers if c.status == 'running'])
            self.current_worker_count = worker_count
            return worker_count
        except Exception as e:
            self.log(f"⚠ Error getting worker count: {e}")
            self.publish_event("warn", f"Error getting worker count: {e}")
            return self.current_worker_count
    
    def scale_workers(self, target_count: int) -> bool:
        """
        Scale workers to target count using docker-compose.
        
        Args:
            target_count: Number of worker instances to run
            
        Returns:
            True if successful, False otherwise
        """
        if target_count == self.current_worker_count:
            return True  # Already at target
        
        if not self.docker_client:
            self.log(f"⚠ Docker not available, skipping scale to {target_count}")
            return False
        
        try:
            self.log(f"↻ Scaling workers: {self.current_worker_count} → {target_count}")
            
            # Desired state: scale by adjusting container replicas
            # For Docker Compose, we scale by modifying the service desired count
            containers = self.docker_client.containers.list(
                filters={'label': f'com.docker.compose.service=worker'}
            )
            
            current_running = len([c for c in containers if c.status == 'running'])
            
            if target_count > current_running:
                # Scale up: start additional containers
                diff = target_count - current_running
                self.log(f"  Creating {diff} new worker(s)...")
                
                # Get the first worker container as template
                if containers:
                    template = containers[0]
                    image = template.image
                    env = template.attrs['Config']['Env']
                    networks = template.attrs['NetworkSettings']['Networks']
                    network_name = list(networks.keys())[0] if networks else None
                    
                    for i in range(diff):
                        worker_num = current_running + i + 1
                        env_dict = dict([e.split('=', 1) for e in env if '=' in e])
                        env_dict['WORKER_ID'] = f'worker-{worker_num}'
                        
                        run_kwargs = {
                            'image': image,
                            'name': f'{self.project_name}-worker-{worker_num}',
                            'environment': env_dict,
                            'restart_policy': {'Name': 'unless-stopped'},
                            'detach': True,
                            'labels': {
                                'com.docker.compose.project': self.project_name,
                                'com.docker.compose.service': 'worker',
                            }
                        }
                        if network_name:
                            run_kwargs['network'] = network_name

                        self.docker_client.containers.run(
                            image,
                            **{k: v for k, v in run_kwargs.items() if k != 'image'}
                        )
                        self.log(f"  ✓ Started worker-{worker_num}")
            
            elif target_count < current_running:
                # Scale down: stop extra containers
                diff = current_running - target_count
                self.log(f"  Stopping {diff} worker(s)...")
                
                # Stop the most recently created workers
                running_containers = sorted(
                    [c for c in containers if c.status == 'running'],
                    key=lambda x: x.attrs['State']['StartedAt'],
                    reverse=True
                )
                
                for container in running_containers[:diff]:
                    try:
                        self.log(f"  Stopping {container.name}...")
                        container.stop(timeout=10)
                        container.remove()
                        self.log(f"  ✓ Stopped {container.name}")
                    except Exception as e:
                        self.log(f"  ⚠ Error stopping {container.name}: {e}")
            
            self.current_worker_count = target_count
            self.last_scale_time = time.time()
            self.log(f"✓ Scaled to {target_count} workers")
            self.publish_event(
                "info",
                f"Scaled workers to {target_count}",
                queue_length=self.get_queue_length(),
                workers=target_count,
            )
            try:
                self.P_SCALE_EVENTS.inc()
            except Exception:
                pass
            return True
            
        except Exception as e:
            self.log(f"✗ Scaling error: {e}")
            self.publish_event("error", f"Scaling error: {e}")
            return False
    
    def should_scale_up(self, queue_length: int) -> bool:
        """Check if we should scale up."""
        if self.current_worker_count >= self.max_workers:
            return False
        return queue_length > self.scale_up_threshold
    
    def should_scale_down(self, queue_length: int) -> bool:
        """Check if we should scale down."""
        if self.current_worker_count <= self.min_workers:
            return False
        return queue_length < self.scale_down_threshold
    
    def can_scale_now(self) -> bool:
        """Check if enough time has passed since last scale."""
        return (time.time() - self.last_scale_time) >= self.cooldown_seconds
    
    def tick(self):
        """One iteration of the autoscaler loop."""
        queue_length = self.get_queue_length()
        current_workers = self.get_current_workers()
        
        # Log current state
        self.log(f"Queue: {queue_length} jobs | Workers: {current_workers}/{self.max_workers}")
        self.publish_event("debug", "Tick", queue_length=queue_length, workers=current_workers)
        
        # Check if we should scale
        if not self.can_scale_now():
            cooldown_remaining = int(self.cooldown_seconds - (time.time() - self.last_scale_time))
            self.log(f"⏳ Cooldown active ({cooldown_remaining}s remaining), skipping scale decision")
            return
        
        if self.should_scale_up(queue_length):
            target = min(current_workers + 1, self.max_workers)
            self.scale_workers(target)
        
        elif self.should_scale_down(queue_length):
            target = max(current_workers - 1, self.min_workers)
            self.scale_workers(target)
    
    def run(self):
        """Main autoscaler loop."""
        self.log(f"Starting autoscaler (polling every {self.poll_interval}s)")
        
        try:
            while True:
                self.tick()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            self.log("Shutting down autoscaler")
        except Exception as e:
            self.log(f"Fatal error: {e}")
            raise


if __name__ == "__main__":
    autoscaler = QueueBasedAutoscaler()
    autoscaler.run()
