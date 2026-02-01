FROM python:3.9-slim

WORKDIR /app

COPY signal_layer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY signal_layer/src /app/src

ENV PYTHONPATH=/app

CMD ["python", "src/signal_orchestrator.py"]
