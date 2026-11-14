# The demo API: one small container. Runs anywhere that runs a container (Fly.io, Render,
# Google Cloud Run). Set ANTHROPIC_API_KEY and DEMO_ALLOWED_ORIGINS as secrets on the host.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY demo_api ./demo_api
RUN useradd --create-home demo && mkdir -p /data && chown demo /data
USER demo
ENV PORT=8080 DEMO_DB=/data/runs.db
EXPOSE 8080
CMD ["sh", "-c", "uvicorn demo_api.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
