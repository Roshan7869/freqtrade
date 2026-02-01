FROM python:3.9-slim

WORKDIR /app

COPY data_layer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY data_layer/src /app/src

ENV PYTHONPATH=/app

CMD ["python", "src/market_data_ingestion.py", "ticks"]
