FROM python:3.11-slim

WORKDIR /app

COPY autoscaler/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY autoscaler /app

CMD ["python", "autoscaler.py"]
