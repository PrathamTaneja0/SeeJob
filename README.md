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

### OpenRouter (free models)

SeeJob uses an OpenAI-compatible chat API. [OpenRouter](https://openrouter.ai/) works with the same client — set your OpenRouter key and base URL in `.env`:

```bash
SEEJOB_OPENAI_API_KEY=sk-or-v1-your-key-from-openrouter.ai/keys
SEEJOB_OPENAI_BASE_URL=https://openrouter.ai/api/v1
SEEJOB_LLM_MODEL=openrouter/free
```

`openrouter/free` is OpenRouter’s free router (picks from available free models). For a specific model, use its slug from the OpenRouter catalog. Document generation, job scoring, Q&A answers, and field mapping all read `SEEJOB_OPENAI_BASE_URL` and `SEEJOB_LLM_MODEL` from settings.

For local dev without an API key, set `SEEJOB_ALLOW_MOCK_LLM=true` (development/test only).

### API docs

- Swagger UI: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Dev commands

```bash
pytest
ruff check seejob tests
alembic upgrade head
seejob-tick --skip-sourcing   # one scheduler tick (pipeline queue only)
seejob-tick --dry-run         # sourcing + pipeline without form submit
```

### Scheduler (Phase 5)

The orchestrator advances approved applications through document generation and browser apply on each tick — not as a 24/7 daemon. Configure cron or run manually:

```bash
seejob-tick                      # sourcing pass + pipeline queue
seejob-tick --skip-sourcing      # pipeline queue only
seejob-tick --person-id 1        # score ingested jobs for person 1
```

- **Rate limits**: `PolicyConfig.rate_limits_json` caps applies per platform per UTC day
- **Interrupts**: captcha/login pauses set `needs_manual` / `auth_required`; resume via `POST /api/v1/applications/{id}/resume`
- **Events**: `GET /api/v1/events` (poll) or `GET /api/v1/events/stream` (SSE) for dashboard feed

## Dashboard (Phase 6)

React control UI in `dashboard/` — pipeline kanban, job queue, application detail, profiles, settings, and live agent console.

### Dev (API + Vite)

Terminal 1 — API:

```bash
seejob
```

Terminal 2 — dashboard (proxies `/api` to `:8000`):

```bash
cd dashboard
npm install
npm run dev
```

Open http://localhost:5173

**502 Bad Gateway on `/api/*`?** Vite proxies to `http://127.0.0.1:8000`. A 502 means the SeeJob API is not running or is on a different port. Fix:

1. In a separate terminal, from the repo root: `seejob` (or `uvicorn seejob.api.app:app --host 127.0.0.1 --port 8000`)
2. Confirm the API responds: http://127.0.0.1:8000/health → `{"status":"ok"}`
3. If you changed `SEEJOB_PORT` in `.env`, set `VITE_API_URL=http://127.0.0.1:<port>` in `dashboard/.env` so the proxy matches

Optional: set `VITE_API_URL=http://127.0.0.1:8000` in `dashboard/.env` to call the API directly (CORS must include `:5173` — see `SEEJOB_CORS_ORIGINS` in `.env.example`).

### Production build

```bash
cd dashboard
npm run build
seejob   # serves dashboard/dist at / when present
```

Then open http://127.0.0.1:8000/

### Dashboard scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Vite dev server on :5173 |
| `npm run build` | Typecheck + production bundle to `dist/` |
| `npm run test` | Vitest component smoke tests |
| `npm run preview` | Preview production build locally |


## Workers (scheduled, not 24/7)

SeeJob workers are **single-tick** CLIs meant for cron or Task Scheduler — not always-on daemons.

| Command | Purpose |
|---------|---------|
| `seejob-sourcing` | One sourcing pass: poll RSS/API sources, ingest and score jobs |
| `seejob-tick` | Full scheduler tick: sourcing + approved pipeline queue (doc gen + apply) |

Configure cadence via `PolicyConfig.sourcing_interval_minutes` (default 60). Example cron (every hour):

```bash
0 * * * * cd /path/to/SeeJob && .venv/bin/seejob-tick
```

`seejob-tick` flags:

- `--person-id N` — score ingested jobs for a specific profile
- `--dry-run` — fill forms without submitting
- `--skip-sourcing` — only process the approved applications pipeline queue

Pipeline orchestration lives in `seejob/services/pipeline.py`. Rate limits are enforced per platform per day via `AgentRun` audit rows. Interrupt states (`needs_manual`, `auth_required`) store JSON metadata on the application; resume with `POST /api/v1/applications/{id}/resume`.

Agent events stream at `GET /api/v1/events/stream` (SSE) for dashboard integration.

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
dashboard/    # React control UI (Phase 6)
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

### Phase 5 (current)
- Pipeline orchestrator (`run_pipeline_for_application`)
- Scheduled worker (`seejob-tick`) — sourcing + approved queue per tick
- Per-platform daily rate limits via `AgentRun` audit log
- Interrupt/resume flow for captcha and auth
- SSE event stream for dashboard

### Phase 6 (current)
- React control dashboard (`dashboard/`) — Vite + TanStack Query + Tailwind
- Pipeline kanban, job queue, application detail, profiles, settings, agent console
- FastAPI serves `dashboard/dist` at `/` when built; CORS for local dev

### Phase 7 (current)
- Gmail OTP fetcher (`seejob/integrations/gmail.py`) — IMAP with MCP-ready interface
- Site account CRUD (`/api/v1/site-accounts`) — Fernet-encrypted credentials, masked passwords
- Auth service (`seejob/services/auth.py`) — credential lookup, login hooks, session sync
- CapSolver integration (`seejob/integrations/capsolver.py`) — Turnstile/reCAPTCHA when API key set
- Manual OTP injection (`POST /api/v1/applications/{id}/provide-otp`)
- Docker Compose production deploy (`docker-compose.yml`)

## Production deploy (Docker)

### Prerequisites

- Docker and Docker Compose
- Fernet key and secrets in `.env`

### Build and run

```bash
# Build dashboard bundle (served by API at /)
cd dashboard && npm install && npm run build && cd ..

# Configure environment
cp .env.example .env
# Set SEEJOB_FERNET_KEY, GMAIL_* (optional OTP), SEEJOB_CAPSOLVER_API_KEY (optional)

docker compose up -d --build
```

API: http://localhost:8000 — Swagger at `/docs`.

### Environment variables (production)

| Variable | Purpose |
|----------|---------|
| `SEEJOB_FERNET_KEY` | Encrypt site credentials and session cookies |
| `SEEJOB_SECRET_KEY` | API signing (future auth) |
| `SEEJOB_DATABASE_URL` | Set automatically in compose to PostgreSQL |
| `GMAIL_IMAP_HOST` | Gmail IMAP host (default `imap.gmail.com`) |
| `GMAIL_USER` | Gmail address for OTP fetch |
| `GMAIL_APP_PASSWORD` | Gmail app password (not account password) |
| `SEEJOB_CAPSOLVER_API_KEY` | CapSolver API key for captcha auto-solve |
| `SEEJOB_VECTOR_ENABLED` | Enable Chroma vector store |
| `SEEJOB_OPENAI_API_KEY` | LLM document generation (OpenAI or OpenRouter key) |
| `SEEJOB_OPENAI_BASE_URL` | OpenAI-compatible API base (default OpenAI; use OpenRouter URL for free tier) |
| `SEEJOB_LLM_MODEL` | Chat model slug (e.g. `gpt-4o-mini` or `openrouter/free`) |

### Gmail OTP (optional)

`GMAIL_USER` and `GMAIL_APP_PASSWORD` are **optional**. They are only used for automatic one-time-password fetch over IMAP during ATS login flows.

If you skip Gmail setup, you can still apply to jobs:

- Paste the OTP in the dashboard: `POST /api/v1/applications/{id}/provide-otp`
- Or complete login/captcha in the browser when the application enters `needs_manual`

See [docs/CAPTCHA.md](docs/CAPTCHA.md) for captcha handling and [docs/DEPLOY_CLOUDFLARE.md](docs/DEPLOY_CLOUDFLARE.md) for Cloudflare deployment options.

### Optional Chroma profile

```bash
docker compose --profile chroma up -d
```

Chroma listens on port 8100 when the profile is active.


## Security

- Never commit .env, Fernet keys, or reference/ contents
- SiteAccount stores only Fernet-encrypted credentials
- Default policy requires approval before document use and submission

## License

MIT
