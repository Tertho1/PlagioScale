#!/usr/bin/env python3
import redis, json, time, sys

REDIS_HOST = 'localhost'
REDIS_PORT = 6379

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
queue_len = 0
try:
    queue_len = r.llen('job_queue')
except Exception:
    pass

event = {
    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'level': 'info',
    'message': f'Manual scale to {n} workers (demo)',
    'queue_length': queue_len,
    'workers': n
}

r.lpush('autoscaler_events', json.dumps(event))
r.ltrim('autoscaler_events', 0, 99)
print('Pushed demo event to Redis:', event)
