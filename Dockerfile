# ==========================================
# BUILDER
# ==========================================
FROM python:3.14-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

RUN apk add --no-cache gcc musl-dev libffi-dev build-base

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# ==========================================
# RUNNER
# ==========================================
FROM python:3.14-alpine AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

COPY . .

RUN mkdir -p logs && \
    addgroup -S appgroup && \
    adduser -S appuser -G appgroup && \
    chown -R appuser:appgroup /app logs

USER appuser

EXPOSE 8000


CMD ["sh", "-c", "exec gunicorn app.main:app --bind 0.0.0.0:8000 --worker-class uvicorn.workers.UvicornWorker --workers $((2 * $(nproc) + 1))"]