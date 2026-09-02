# Pinned by digest-free tag for a deterministic, reproducible build.
FROM python:3.11.9-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Non-root at runtime.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080

# 2 workers is plenty for a single-machine, low-RAM target.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "30", "app:app"]
