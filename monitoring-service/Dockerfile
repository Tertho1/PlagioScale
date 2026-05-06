FROM python:3.11-slim

WORKDIR /app

COPY monitoring-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitoring-service /app

CMD ["python", "main.py"]
