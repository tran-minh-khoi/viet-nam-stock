FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VNSTOCK_HOME=/data/vnstock

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY api.py config.py ./

# Run as a normal user; /data keeps the vnstock login + device id across restarts
RUN useradd --create-home --uid 1000 app && mkdir -p /data/vnstock && chown -R app /data
USER app
VOLUME /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

# One worker on purpose: the in-memory cache and request de-duplication are per process,
# and one async worker is plenty for a personal API. Add Redis before adding workers.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
