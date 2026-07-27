FROM dhi.io/python:3.11-dev AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y gcc g++ make && rm -rf /var/lib/apt/lists/*

COPY worker-service/requirements.txt .

RUN python -m venv /build/venv && \
    /build/venv/bin/pip install --no-cache-dir torch --no-deps --index-url https://download.pytorch.org/whl/cpu && \
    /build/venv/bin/pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/storage /app/logs /app/hf_cache

FROM dhi.io/python:3.11

WORKDIR /app

COPY --from=builder --chown=65532:65532 /app/storage /app/storage
COPY --from=builder --chown=65532:65532 /app/logs /app/logs
COPY --from=builder --chown=65532:65532 /app/hf_cache /app/hf_cache

COPY --from=builder --chown=65532:65532 /build/venv/lib/python3.11/site-packages /usr/lib/python3.11/site-packages

COPY --chown=65532:65532 shared /app/shared
COPY --chown=65532:65532 worker-service /app

CMD ["python", "worker.py"]
