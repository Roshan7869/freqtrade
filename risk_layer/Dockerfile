FROM python:3.9-slim

WORKDIR /app

COPY risk_layer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY risk_layer/src /app/src

ENV PYTHONPATH=/app

CMD ["python", "src/capital_manager.py"]
