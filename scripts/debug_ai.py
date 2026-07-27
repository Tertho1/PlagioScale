import requests, time, json

r = requests.post('http://localhost:8000/submit', json={'text':'This is a test for AI detection pipeline.'}, timeout=10)
print('submit:', r.status_code)
data = r.json()
print('submit response:', json.dumps(data, indent=2))
job_id = data['job_id']

for i in range(30):
    r = requests.get(f'http://localhost:8000/result/{job_id}', timeout=5)
    if r.status_code == 200:
        d = r.json()
        s = d.get('status')
        res = d.get('result')
        print(f'poll {i}: status={s}', f'result keys={list(res.keys()) if res else "no result"}')
        if s in ('completed', 'ready'):
            print('FINAL:', json.dumps(d, indent=2))
            break
    else:
        print(f'poll {i}: {r.status_code} {r.text[:100]}')
    time.sleep(2)
