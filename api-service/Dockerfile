FROM python:3.11-slim

WORKDIR /app

# Install dependencies first
COPY api-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY shared /app/shared

# Copy API service
COPY api-service /app

EXPOSE 8000

CMD ["python", "main.py"]
