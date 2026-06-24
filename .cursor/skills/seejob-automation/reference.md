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

All prefixed with `SEEJOB_`. See `.env.example` for full list.

Critical:
- `SEEJOB_FERNET_KEY` — required for `SiteAccount` encryption
- `SEEJOB_DATABASE_URL` — `sqlite:///./seejob.db` (dev) or PostgreSQL URL (prod)
- `SEEJOB_SECRET_KEY` — API signing (future auth)

## BrowserActuator interface

Located in `seejob/browser/interfaces.py`. Phase 2 Playwright implementation must:

1. Load `BrowserSession.profile_dir` for cookie persistence
2. Return `BrowserActionResult.CAPTCHA` → orchestrator sets `needs_manual`
3. Return `BrowserActionResult.AUTH_REQUIRED` → orchestrator sets `auth_required`
4. Never call `submit_form()` without submit approval gate
5. Call `save_session()` after successful auth

## Agent interfaces

Located in `seejob/agents/interfaces.py`:

- `DocumentGenerator` — CV and cover letter with `TruthfulnessConstraint`
- `ScreeningAnswerer` — Q&A with cache-first lookup
- `JobScorer` — fit score 0.0–1.0
- `Orchestrator` — pipeline step advancement and approval requests

## Screening question hashing

```python
from seejob.services.screening import hash_question, normalize_question

h = hash_question("Why do you want to work here?")
# Lookup ScreeningAnswer where person_id=X and question_hash=h
```

Normalization: lowercase, collapse whitespace, strip punctuation.

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

## Testing focus areas

1. State machine — every new transition must have tests in `tests/test_state_machine.py`
2. Schemas — validation rules in `tests/test_profile_schemas.py`
3. API smoke — `tests/test_api.py` with in-memory SQLite

## Git rules for agents

- Never commit `.env`, `*.db`, `reference/*`, `generated/`, `browser_profiles/`
- Never commit real resumes or credentials
- Run `pytest` before pushing model or state machine changes
