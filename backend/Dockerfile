# Production image for the FastAPI backend.
#   docker build -t ai-knowledge-base-api .
#   docker run --env-file .env -p 8000:8000 ai-knowledge-base-api
# Hosts that assign a port (Render, Railway, Fly, Cloud Run) set $PORT.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1     PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Only the app: migrations and scripts/ are dev tools run from a checkout.
COPY app ./app

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
# --proxy-headers: trust X-Forwarded-* from the host's load balancer.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
