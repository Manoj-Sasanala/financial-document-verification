# DEP-01: single-service demo deployment.
#
# Build (requires a Docker daemon, unavailable in some CI sandboxes):
#   docker build -t kyc-risk-copilot .
# Run:
#   docker run --rm -p 8000:8000 \
#     -e CASE_DB_PATH=/data/db.sqlite3 \
#     -v kyc-data:/data \
#     kyc-risk-copilot
# Health: GET http://localhost:8000/api/v1/health -> {"status": "ok"}
#
# Model weights are baked from the local Hugging Face cache at build time
# when available; otherwise the image downloads
# sentence-transformers/all-MiniLM-L6-v2 on first startup (network needed).

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CASE_DB_PATH=/data/db.sqlite3 \
    HF_HUB_OFFLINE=0

WORKDIR /srv/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY data/ ./data/
COPY artifacts/ ./artifacts/
COPY scripts/ ./scripts/
COPY README.md ./

RUN mkdir -p /data && python -c "from app.db.init_db import initialize_database; initialize_database('/data/db.sqlite3'); print('db ready')"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
