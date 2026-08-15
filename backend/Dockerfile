# Capybara trading engine + control API.
# Long-running process (loop + WebSocket) — deploy on an ALWAYS-ON host, not Vercel.
FROM python:3.11-slim

WORKDIR /app

# System deps kept minimal; numpy/pandas ship wheels.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CAPYBARA_API_HOST=0.0.0.0 \
    CAPYBARA_API_PORT=8000 \
    CAPYBARA_DB_PATH=/data/capybara.db

COPY pyproject.toml README.md ./
COPY capybara ./capybara

RUN pip install --upgrade pip && pip install .

# Persist the SQLite state/audit DB across restarts.
VOLUME ["/data"]
EXPOSE 8000

# Healthcheck hits the API's /health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8000/health'); " || exit 1

# Start the live paper-trading loop + control API.
CMD ["capybara", "run"]
