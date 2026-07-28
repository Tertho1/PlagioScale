import time

import requests

r = requests.post('http://localhost:8000/submit', json={'text':'This is a test for AI detection pipeline.'}, timeout=10)
print('submit:', r.status_code, r.json())
job_id = r.json()['job_id']

for i in range(60):
    r = requests.get(f'http://localhost:8000/result/{job_id}', timeout=5)
    d = r.json()
    s = d.get('status')
    print(f'poll {i}: {r.status_code} status={s}')
    if s and s.lower() in ('completed', 'ready'):
        print('RESULT:', d.get('result'))
        break
    time.sleep(2)
