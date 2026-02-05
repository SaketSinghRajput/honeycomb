#!/bin/sh
# Entrypoint for the Scam Honeypot backend.
# Reads API_WORKERS and LOG_LEVEL environment variables and launches uvicorn.

: "${API_WORKERS:=1}"
: "${LOG_LEVEL:=info}"

echo "Starting uvicorn with workers=${API_WORKERS} log_level=${LOG_LEVEL}"

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${API_WORKERS}" \
  --log-level "${LOG_LEVEL}"
