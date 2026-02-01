FROM python:3.9-slim

WORKDIR /app

COPY analysis_layer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY analysis_layer/src /app/src

ENV PYTHONPATH=/app

CMD ["python", "src/regime_analyzer.py"]
