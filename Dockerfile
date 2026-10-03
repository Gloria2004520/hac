FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOST=0.0.0.0 \
    VIDEO_BACKEND_URL=http://127.0.0.1:8000 \
    DATABASE_URL=sqlite:////data/cookclip.db \
    LOCAL_STORAGE_ROOT=/data/storage

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY scripts/start-production.sh ./scripts/start-production.sh

RUN chmod +x ./scripts/start-production.sh \
    && mkdir -p /data/storage

EXPOSE 8080

CMD ["./scripts/start-production.sh"]
