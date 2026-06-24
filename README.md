# SeeJob

Autonomous job application system — local-first orchestrator with human-in-the-loop approval gates, Q&A caching, and ATS session persistence.

## Architecture

SeeJob separates orchestration (planning, scoring, document generation, policy) from actuation (browser automation, form filling). All automation runs locally; credentials are encrypted at rest; submissions require explicit approval by default.

### Design principles

| Principle | Implementation |
|-----------|----------------|
| No 24/7 initially | Scheduled sourcing via cron (SourcingWorker) |
| Approval before submit | require_doc_approval + require_submit_approval in PolicyConfig |
| Q&A bank caching | ScreeningAnswer.question_hash (SHA-256 of normalized question) |
| ATS session persistence | SiteAccount.session_data_encrypted + seejob/data/browser_profiles/ |
| Rate limits per platform | PolicyConfig.rate_limits_json |
| Truthfulness guard | TruthfulnessConstraint in agents — no fabricated experience |
| Human-in-the-loop | needs_manual state for captcha / manual intervention |
| Local-first | SQLite default; all data stays on your machine |

### Application state machine

discovered → scored → pending_approval → generating_docs → docs_ready → auth_required? → filling → submitted

Terminal state: submitted. Failed applications can retry from discovered, scored, or pending_approval.

## Quick start

### Prerequisites

- Python 3.11+
- Git

### Setup

```bash
git clone git@github.com:PrathamTaneja0/SeeJob.git
cd SeeJob

python -m venv .venv
.venv\Scripts\activate

pip install -e ".[dev]"

# Playwright browser (required for form fill)
playwright install chromium

cp .env.example .env

alembic upgrade head

seejob
```

Generate Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add to .env as SEEJOB_FERNET_KEY=...

### API docs

- Swagger UI: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Dev commands

```bash
pytest
ruff check seejob tests
alembic upgrade head
```

## Project structure

```
seejob/
  api/          # FastAPI routes
  core/         # config, security, database
  models/       # SQLAlchemy ORM
  schemas/      # Pydantic schemas
  services/     # business logic
  workers/      # scheduled jobs
  browser/      # Playwright actuator (Phase 4)
  agents/       # orchestration interfaces (Phase 1)
tests/
.cursor/skills/seejob-automation/
reference/      # gitignored
alembic/
```

## Phase roadmap

### Phase 0 (current)
- Project structure, models, API, state machine, tests, Cursor skill

### Phase 1
- LLM document generation, job scoring, Q&A vector cache, scheduled sourcing

### Phase 2
- Playwright automation, ATS session persistence, captcha/manual flow

### Phase 3
- PostgreSQL, Docker Compose, dashboard UI

## Security

- Never commit .env, Fernet keys, or reference/ contents
- SiteAccount stores only Fernet-encrypted credentials
- Default policy requires approval before document use and submission

## License

MIT
