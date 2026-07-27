FROM dhi.io/python:3.11-alpine-dev AS builder

WORKDIR /build

COPY monitoring-service/requirements.txt .

RUN python -m venv /build/venv && \
    /build/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM dhi.io/python:3.11-alpine

WORKDIR /app

COPY --from=builder --chown=0:0 /build/venv/lib/python3.11/site-packages /usr/lib/python3.11/site-packages

COPY --chown=65532:65532 monitoring-service /app

EXPOSE 8090

CMD ["python", "main.py"]
