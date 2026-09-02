# Pinned base for a deterministic, reproducible build.
FROM python:3.11.9-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY data ./data

RUN useradd --create-home --uid 10002 appuser
USER appuser

EXPOSE 9000

CMD ["gunicorn", "--bind", "0.0.0.0:9000", "--workers", "2", "--timeout", "30", "app:app"]
