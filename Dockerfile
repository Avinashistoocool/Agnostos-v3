FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    AGNOSTOS_DATA=/data PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
COPY server/requirements.txt ./server-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r server-requirements.txt

COPY outreach ./outreach
COPY server ./server
COPY web ./web
COPY sources.yaml ./

RUN useradd -m app && mkdir -p /data && chown app /data
USER app
VOLUME ["/data"]
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT}"]
