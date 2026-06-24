---
name: seejob-automation
description: >-
  Guides development of SeeJob autonomous job application system — orchestrator
  vs actuator architecture, approval gates, state machine, Q&A caching, rate
  limits, and truthfulness guards. Use when working on SeeJob job sourcing,
  application pipeline, document generation, browser automation, or ATS form
  filling.
---

# SeeJob Automation

## Architecture

SeeJob is **local-first** with strict separation:

| Layer | Package | Responsibility |
|-------|---------|----------------|
| Orchestrator | `seejob/agents/` + `seejob/services/` | Plan, score, generate docs, answer screening Qs, pipeline |
| Actuator | `seejob/browser/` | Playwright form fill, upload, submit |
| API | `seejob/api/` | REST endpoints, approval gates, SSE events |
| Workers | `seejob/workers/` | Scheduled sourcing and pipeline ticks (cron, not 24/7) |
| Integrations | `seejob/integrations/` | Gmail OTP, CapSolver captcha |
| Data | `seejob/models/` | SQLAlchemy + optional ChromaDB vectors |
| Dashboard | `dashboard/` | React control UI |

**Never** mix orchestration logic into browser code or vice versa.

See [ARCHITECTURE.md](../../../ARCHITECTURE.md) for system diagram and data flow.

## Runtime workflow

```
1. SourcingWorker (seejob-sourcing / seejob-tick) → Job records
2. JobScorer → Application status: discovered → scored
3. Policy check (min_fit_score, filters, rate limits)
4. pending_approval → human approves job targeting
5. generating_docs → DocumentGenerator (truthfulness guard ON)
6. docs_ready → human previews markdown/PDF (require_doc_approval)
7. auth_required? → SiteAccount session or manual login
8. filling → PlaywrightActuator fills form, uses ScreeningAnswer cache
9. Submit gate → human approves (require_submit_approval)
10. submitted → audit in AgentRun
```

On captcha or unknown fields: transition to `needs_manual`, pause automation. Resume via API or dashboard.

## State machine rules

Valid transitions live in `seejob/services/state_machine.py`. Always use `transition()` — never set `Application.status` directly without validation.

Key gates:
- `pending_approval` — before doc generation
- `docs_ready` — document preview before filling
- `require_submit_approval` in PolicyConfig — before `submit_form()`

## Agent rules

### Truthfulness
- Document generation MUST use verified `Person`, `Experience`, `Education`, `Skill` data only
- Set `TruthfulnessConstraint.allow_inference=False` by default
- Run `critique_documents` before marking docs approved
- Never fabricate employers, degrees, or skills

### Approval gates
- Check `PolicyConfig.require_doc_approval` before filling forms
- Check `PolicyConfig.require_submit_approval` before `BrowserActuator.submit_form()`
- Set `GeneratedDocument.approved=True` only after human or explicit API approval

### Secrets
- Use `encrypt_value()` / `decrypt_value()` from `seejob/core/security.py`
- Never log, commit, or print credentials, Fernet keys, or session cookies
- Store ATS cookies in `SiteAccount.session_data_encrypted` only

### Rate limits
- Call `get_platform_daily_limit()` before each apply attempt
- Respect per-platform limits in `rate_limits_json`
- Enforced via `AgentRun` audit rows in `seejob/services/rate_limit.py`

### Q&A caching
- Hash questions with `hash_question()` before lookup
- Prefer cached `ScreeningAnswer` hits; increment `times_used`
- Only generate new answers when cache misses

## Phased checklist (all complete)

### Phase 0 — foundation ✓
- [x] Models, migrations, API, state machine
- [x] Policy config, encryption interfaces
- [x] Browser/agent interfaces

### Phase 1 — intelligence ✓
- [x] `DocumentGenerator` with LLM + truthfulness critic
- [x] `JobScorer` / scoring service
- [x] `ScreeningAnswerer` + Q&A bank + optional ChromaDB
- [x] `SourcingWorker` with RSS/manual sources
- [x] Document preview and PDF export endpoints

### Phase 2 — browser automation ✓
- [x] `PlaywrightActuator` implementing `BrowserActuator`
- [x] Session persistence to `browser_profiles/` and `SiteAccount`
- [x] `ATSLearning` read/write on successful fills
- [x] `needs_manual` flow for captcha

### Phase 3 — production data ✓
- [x] PostgreSQL support, Docker Compose
- [x] Alembic migrations for prod schema

### Phase 4 — pipeline orchestration ✓
- [x] `run_pipeline_for_application` in `seejob/services/pipeline.py`
- [x] `seejob-tick` scheduler worker
- [x] Per-platform daily rate limits
- [x] Interrupt/resume for captcha and auth
- [x] SSE event stream (`GET /api/v1/events/stream`)

### Phase 5 — dashboard ✓
- [x] React control UI (`dashboard/`) — Vite + TanStack Query + Tailwind
- [x] Pipeline kanban, job queue, application detail, profiles, settings, agent console
- [x] FastAPI serves `dashboard/dist` at `/` when built

### Phase 6 — auth & integrations ✓
- [x] Site account CRUD (`/api/v1/site-accounts`) with Fernet encryption
- [x] Auth service (`seejob/services/auth.py`)
- [x] Gmail OTP fetcher (`seejob/integrations/gmail.py`)
- [x] CapSolver integration (`seejob/integrations/capsolver.py`)
- [x] Manual OTP injection (`POST /api/v1/applications/{id}/provide-otp`)

### Phase 7 — CI & docs ✓
- [x] GitHub Actions CI (pytest + dashboard build)
- [x] `ARCHITECTURE.md` system overview
- [x] Skill and reference docs aligned with implementation

## Code conventions

- Type hints on all public functions
- Business logic in `services/`, not route handlers
- New models require Alembic migration
- Tests for state machine changes and schema validation
- Run `pytest` and `cd dashboard && npm run build` before pushing

## Additional resources

- Full architecture and API details: [reference.md](reference.md)
- System overview diagram: [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- Project README: [README.md](../../../README.md)
