FROM python:3.9-slim

WORKDIR /app

COPY execution_layer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY execution_layer/src /app/src

ENV PYTHONPATH=/app

CMD ["python", "src/order_executor.py"]
