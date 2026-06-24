# SeeJob Reference

## Data model relationships

```
Person
 ├── Experience, Education, Skill
 ├── ScreeningAnswer (Q&A bank, keyed by question_hash)
 ├── SiteAccount (encrypted credentials + session)
 └── Application
      ├── Job
      └── GeneratedDocument (cv, cover_letter)
```

Standalone tables: `ATSLearning`, `AgentRun`, `PolicyConfig`, `Job`

## ApplicationStatus enum

| Status | Meaning |
|--------|---------|
| `discovered` | Job linked to person, not yet scored |
| `scored` | Fit score computed |
| `pending_approval` | Awaiting human approval to proceed |
| `generating_docs` | LLM generating tailored documents |
| `docs_ready` | Documents ready for preview |
| `auth_required` | ATS login needed |
| `filling` | Browser filling application form |
| `submitted` | Successfully submitted (terminal) |
| `failed` | Error occurred; may retry |
| `needs_manual` | Captcha or manual intervention required |

## PolicyConfig fields

| Field | Default | Purpose |
|-------|---------|---------|
| `auto_apply` | `false` | Skip approval gates (not recommended) |
| `require_doc_approval` | `true` | Gate before form filling |
| `require_submit_approval` | `true` | Gate before submit |
| `min_fit_score` | `0.6` | Minimum score to proceed |
| `daily_apply_limit` | `10` | Global daily cap |
| `rate_limits_json` | `{"default": 10}` | Per-platform daily limits |
| `sourcing_enabled` | `true` | Enable scheduled sourcing |
| `sourcing_schedule` | `0 8 * * *` | Cron expression (daily 8am) |

## Environment variables

All prefixed with `SEEJOB_` unless noted. See `.env.example` for full list.

Critical:
- `SEEJOB_FERNET_KEY` — required for `SiteAccount` encryption
- `SEEJOB_DATABASE_URL` — `sqlite:///./seejob.db` (dev) or PostgreSQL URL (prod)
- `SEEJOB_SECRET_KEY` — API signing (future auth)

Integrations (optional):
- `GMAIL_USER`, `GMAIL_APP_PASSWORD` — IMAP OTP fetch
- `SEEJOB_CAPSOLVER_API_KEY` — captcha auto-solve
- `SEEJOB_OPENAI_API_KEY` — LLM document generation
- `SEEJOB_ALLOW_MOCK_LLM` — dev/test only; blocked in production

## BrowserActuator (implemented)

`PlaywrightActuator` in `seejob/browser/actuator.py` implements `seejob/browser/interfaces.py`:

1. Loads `BrowserSession.profile_dir` for cookie persistence
2. Returns `BrowserActionResult.CAPTCHA` → orchestrator sets `needs_manual`
3. Returns `BrowserActionResult.AUTH_REQUIRED` → orchestrator sets `auth_required`
4. Never calls `submit_form()` without submit approval gate
5. Calls `save_session()` after successful auth
6. Uses `field_mapper.py`, `form_filler.py`, `dom_extractor.py` for ATS forms
7. Writes `ATSLearning` records on successful field mappings

## Agent implementations

| Interface | Implementation | Location |
|-----------|----------------|----------|
| `DocumentGenerator` | LLM + truthfulness critic | `seejob/agents/document_generator.py` |
| `ScreeningAnswerer` | Cache-first Q&A | `seejob/agents/answer_generator.py` |
| `JobScorer` | Fit scoring | `seejob/services/scoring.py` |
| Pipeline | Doc gen + apply orchestration | `seejob/services/pipeline.py` |

## Workers

| CLI | Module | Purpose |
|-----|--------|---------|
| `seejob` | `seejob/api/app.py` | FastAPI server |
| `seejob-sourcing` | `seejob/workers/sourcing.py` | One sourcing pass |
| `seejob-tick` | `seejob/workers/scheduler.py` | Sourcing + pipeline queue |

Sourcing sources: RSS (`seejob/services/sourcing/sources/rss.py`), manual ingest, board API stub.

## API routes

| Prefix | Module |
|--------|--------|
| `/api/v1/profiles` | Profile CRUD, resume upload |
| `/api/v1/jobs` | Job queue, ingest |
| `/api/v1/applications` | Pipeline, approvals, resume, OTP |
| `/api/v1/events` | Poll + SSE stream |
| `/api/v1/policy` | PolicyConfig |
| `/api/v1/site-accounts` | Encrypted ATS credentials |
| `/health` | Health check |

## Screening question hashing

```python
from seejob.services.screening import hash_question, normalize_question

h = hash_question("Why do you want to work here?")
# Lookup ScreeningAnswer where person_id=X and question_hash=h
```

Normalization: lowercase, collapse whitespace, strip punctuation.

## Interrupts and resume

Interrupt metadata stored as JSON on `Application`. States: `needs_manual`, `auth_required`.

- Resume: `POST /api/v1/applications/{id}/resume`
- OTP injection: `POST /api/v1/applications/{id}/provide-otp`
- Auth service: `seejob/services/auth.py`

## API error codes

| Code | When |
|------|------|
| 404 | Profile/job/application not found |
| 409 | Invalid state machine transition |
| 422 | Pydantic validation failure |

## Migration commands

```bash
alembic upgrade head          # apply all
alembic downgrade -1          # rollback one
alembic revision --autogenerate -m "msg"  # new migration
```

## Dashboard

React app in `dashboard/` — pages: PipelineKanban, JobQueue, ApplicationDetail, ProfileEditor, Settings, AgentConsole.

- Dev: `npm run dev` on :5173 (proxies `/api` to :8000)
- Prod: `npm run build` → served by FastAPI at `/`

## Testing focus areas

1. State machine — `tests/test_state_machine.py`
2. Schemas — `tests/test_profile_schemas.py`
3. API smoke — `tests/test_api.py` with in-memory SQLite
4. Pipeline — `tests/test_pipeline.py`, `tests/test_scheduler.py`
5. Browser apply — `tests/test_browser_apply.py` (mocked Playwright)
6. Auth/integrations — `tests/test_auth.py`, `tests/test_gmail_otp.py`, `tests/test_capsolver.py`

CI: `.github/workflows/ci.yml` runs `pytest` and `dashboard npm run build` on push/PR to `main`.

## Git rules for agents

- Never commit `.env`, `*.db`, `reference/*`, `generated/`, `browser_profiles/`
- Never commit real resumes or credentials
- Run `pytest` before pushing model or state machine changes
