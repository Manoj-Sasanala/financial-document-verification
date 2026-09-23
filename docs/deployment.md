# Deployment (DEP-01 v1.0.0)

## Single-service package

The demo ships as one container (`Dockerfile`) serving the FastAPI app on
port 8000 with SQLite storage. All stages run in-process; no external
vector database or model server is required.

## Run

```sh
docker build -t kyc-risk-copilot .
docker run --rm -p 8000:8000 \
  -e CASE_DB_PATH=/data/db.sqlite3 \
  -v kyc-data:/data \
  kyc-risk-copilot
```

## Verify

```sh
curl http://localhost:8000/api/v1/health
# {"status": "ok"}
```

Upload a synthetic proof-of-address PDF to `/api/v1/cases` with a
`customer_id` form field, then review via `/api/v1/cases/{id}/review`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CASE_DB_PATH` | `/data/db.sqlite3` | SQLite file (mount a volume for persistence, see DEP-02) |
| `LLM_API_KEY` | empty | Optional external LLM key; empty means controlled unavailable explanations |
| `LLM_API_URL` | empty | Optional external LLM endpoint |
| `LLM_MODEL` | `demo-explainer-1.0` | Model label recorded in results |
| `LLM_TIMEOUT_S` | `30` | LLM HTTP timeout in seconds |

## Persistence (DEP-02)

`CASE_DB_PATH` selects the SQLite file. In compose, the `kyc-data` named
volume persists `/data/db.sqlite3` across container restarts and rebuilds:

```sh
docker compose up --build -d
```

Without Docker, point `CASE_DB_PATH` at any durable filesystem path; the
QA-06 restart suite proves file-backed cases survive process restarts.

## Notes

- Model artifacts under `artifacts/` are baked into the image; the
  embedding model additionally resolves from the Hugging Face cache.
- Image build requires a Docker daemon. Where no daemon is available, the
  equivalent `uvicorn app.main:app` runtime is boot-verified instead
  (see DEP-01 implementation record).
