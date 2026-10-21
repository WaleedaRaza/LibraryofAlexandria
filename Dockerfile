FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    useradd --create-home --uid 10001 libxndr && \
    mkdir -p /app/data /app/canon && \
    chown -R libxndr:libxndr /app

COPY --chown=libxndr:libxndr app ./app
COPY --chown=libxndr:libxndr static ./static
COPY --chown=libxndr:libxndr templates ./templates
COPY --chown=libxndr:libxndr library ./library

USER libxndr

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
