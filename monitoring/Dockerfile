FROM python:3.9-slim

WORKDIR /app

COPY monitoring/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY monitoring/src /app/src

ENV PYTHONPATH=/app

CMD ["python", "src/telegram_alerts.py"]
