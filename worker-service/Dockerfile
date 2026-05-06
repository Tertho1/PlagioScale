FROM python:3.11-slim

WORKDIR /app

# Install dependencies first
COPY worker-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY shared /app/shared

# Copy worker service
COPY worker-service /app

CMD ["python", "worker.py"]
