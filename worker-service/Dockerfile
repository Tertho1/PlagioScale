FROM python:3.11-slim

WORKDIR /app

# Install dependencies first
COPY worker-service/requirements.txt .
# Install CPU-only PyTorch without deps (deps come from PyPI below)
RUN pip install --no-cache-dir torch --no-deps --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download SentenceTransformer model for faster startup
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L12-v2')"

# Copy shared utilities
COPY shared /app/shared

# Copy worker service
COPY worker-service /app

CMD ["python", "worker.py"]
