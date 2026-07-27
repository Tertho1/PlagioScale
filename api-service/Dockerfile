FROM dhi.io/python:3.11-alpine-dev AS builder

WORKDIR /build

RUN apk add --no-cache file-dev gcc g++ musl-dev linux-headers make python3-dev

COPY api-service/requirements.txt .

RUN python -m venv /build/venv && \
    /build/venv/bin/pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/uploads /app/logs

FROM dhi.io/python:3.11-alpine

WORKDIR /app

COPY --from=builder /usr/lib/libmagic.so* /usr/lib/

COPY --from=builder --chown=65532:65532 /app/uploads /app/uploads
COPY --from=builder --chown=65532:65532 /app/logs /app/logs

COPY --from=builder --chown=65532:65532 /build/venv/lib/python3.11/site-packages /usr/lib/python3.11/site-packages

COPY --chown=65532:65532 shared /app/shared
COPY --chown=65532:65532 api-service /app

EXPOSE 8000

CMD ["python", "main.py"]
