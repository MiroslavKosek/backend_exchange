# ==========================================
# BUILDER
# ==========================================
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential

WORKDIR /build

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# ==========================================
# RUNNER
# ==========================================
FROM python:3.14-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends openssh-server

WORKDIR /app

RUN echo "root:Docker!" | chpasswd

RUN ssh-keygen -A

COPY ./sshd_config /etc/ssh/.

EXPOSE 2222 80

COPY --from=builder /opt/venv /opt/venv

COPY . .

RUN sed -i 's/\r//' ./start.sh && chmod +x ./start.sh

RUN mkdir -p logs && \
    adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app

EXPOSE 8000

ENTRYPOINT ["./start.sh"]

CMD ["gunicorn", "app.main:app", "--bind", "0.0.0.0:8000", "--worker-class", "uvicorn.workers.UvicornWorker"]