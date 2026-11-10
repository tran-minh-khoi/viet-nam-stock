FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY api.py config.py dnse.py engine.py sources.py ./

# Run as a normal user. /data is where a volume can keep the snapshot (SNAPSHOT_FILE) across
# restarts: docker-compose.yml mounts one; on Railway add a Volume at /data instead (no VOLUME here,
# Railway refuses it).
RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown -R app /data
USER app

# PORT is set by hosts like Railway/Render/Fly; 8000 otherwise
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)"

# One worker on purpose: the /stock/* cache and the upstream budget live in the process.
CMD ["sh", "-c", "exec uvicorn api:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers"]
