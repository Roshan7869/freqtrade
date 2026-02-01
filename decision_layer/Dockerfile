FROM python:3.9-slim

WORKDIR /app

COPY decision_layer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY decision_layer/src /app/src

ENV PYTHONPATH=/app

CMD ["python", "src/decision_engine.py"]
