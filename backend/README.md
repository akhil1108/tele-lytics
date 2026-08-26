# Backend

FastAPI service plus the pipeline worker: one API for the dashboard and the
handset, and the two-stage pipeline that turns a recording into insight.

## Running

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp ../.env.example ../.env        # SQLite and the mock providers work as-is
alembic upgrade head

uvicorn app.main:app --reload     # API   → http://localhost:8000/docs
python -m app.worker              # worker (separate terminal)
```

With `STT_PROVIDER=mock` and `ANALYSIS_PROVIDER=mock` the whole system runs
with no model credentials — useful for development and for the test suite.

Seed a demo organisation:

```bash
python -m scripts.seed --reset --calls 60
# admin@northwind.example.com / northwind-admin-2026
```

## Tests

```bash
pytest          # 74 tests, in-memory SQLite, no external services
ruff check .
```

Coverage is on the parts where a bug is expensive: tenant isolation, the full
recording → transcript → analysis path, retry and non-retry behaviour, policy
resolution including customer opt-out, and the aggregations behind every
dashboard figure.

## Layout

```
app/
  api/v1/      auth agents calls policies analytics tasks mobile ws
  core/        config security deps errors logging
  db/          models enums session base
  llm/         schemas prompts stopwords registry
    stt/       base shared_model mock         ← stage 1 providers
    analysis/  base claude mock               ← stage 2 providers
  services/    pipeline queue storage policies metrics presence
               retention phone duedates timerange
  worker.py    pipeline worker entrypoint
```

## Plugging in your models

**Speech (stage 1).** Set `STT_PROVIDER=shared_model` and point
`STT_ENDPOINT_URL` at your model. The wire contract is
[`docs/STT_CONTRACT.md`](../docs/STT_CONTRACT.md); the adapter tolerates most
of the field-name variation real speech APIs show, so you will usually not need
to change your model's output.

**Insight (stage 2).** Set `ANALYSIS_PROVIDER=claude` and `ANTHROPIC_API_KEY`.
Uses structured outputs, so the response validates against the `CallAnalysis`
schema on arrival — no JSON repair step.

Both are selected in `app/llm/registry.py`. A third provider is a new class
satisfying the protocol in the relevant `base.py` plus one line there.

## Notes worth knowing

**Filler counts are computed in code, not by the model.** `app/llm/stopwords.py`
counts exactly; the model is handed those numbers and asked to judge them. A
model asked to count produces figures that drift between runs, and a dashboard
whose numbers move when nothing changed is one nobody trusts.

**Recording defaults to off.** A number with no policy is not recorded, and an
explicit customer opt-out beats the agent's own settings. See
`app/services/policies.py` — the reasoning is written there.

**The job queue is a Postgres table.** `app/services/queue.py`. A call row and
its pipeline work commit together, which a separate broker cannot give you.
Claiming is atomic; run more workers by starting more processes.

**Both stages are idempotent.** Re-running one replaces its own output and
leaves everything else alone, which is what makes retries safe and lets you
re-run a call after swapping models.

## Environment

Every variable is documented in [`.env.example`](../.env.example). The ones
that matter most:

| Variable            | Default | Notes                                        |
| ------------------- | ------- | -------------------------------------------- |
| `DATABASE_URL`      | SQLite  | Postgres in deployment                       |
| `STT_PROVIDER`      | `mock`  | `shared_model` for your own speech model     |
| `ANALYSIS_PROVIDER` | `mock`  | `claude` for model-backed insight            |
| `STORAGE_BACKEND`   | `local` | `s3` needs `pip install ".[s3]"`             |
| `SECRET_KEY`        | dev key | **Must** be replaced outside development     |
| `MAX_RECORDING_MB`  | `200`   | Hard cap on one upload                       |
| `DEFAULT_RETENTION_DAYS` | `90` | `0` keeps recordings indefinitely           |
