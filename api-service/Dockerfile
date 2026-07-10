FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (libmagic for python-magic)
RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 && rm -rf /var/lib/apt/lists/*

# Install dependencies first
COPY api-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY shared /app/shared

# Copy API service
COPY api-service /app

EXPOSE 8000

CMD ["python", "main.py"]
