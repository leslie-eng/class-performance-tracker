FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --timeout 120 --retries 10 -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && useradd --create-home --uid 1000 classtrack
USER classtrack

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
# Hosts like Render set PORT; docker compose leaves it unset and gets 8000.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers --forwarded-allow-ips '*'"]
