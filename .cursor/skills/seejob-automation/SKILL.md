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
| Orchestrator | `seejob/agents/` | Plan, score, generate docs, answer screening Qs |
| Actuator | `seejob/browser/` | Playwright form fill, upload, submit |
| API | `seejob/api/` | REST endpoints, approval gates |
| Workers | `seejob/workers/` | Scheduled sourcing (cron, not 24/7) |
| Data | `seejob/models/` | SQLAlchemy + optional ChromaDB vectors |

**Never** mix orchestration logic into browser code or vice versa.

## Runtime workflow

```
1. SourcingWorker (scheduled) → Job records
2. ScoringWorker → Application status: discovered → scored
3. Policy check (min_fit_score, filters, rate limits)
4. pending_approval → human approves job targeting
5. generating_docs → DocumentGenerator (truthfulness guard ON)
6. docs_ready → human previews markdown/PDF (require_doc_approval)
7. auth_required? → SiteAccount session or manual login
8. filling → BrowserActuator fills form, uses ScreeningAnswer cache
9. Submit gate → human approves (require_submit_approval)
10. submitted → audit in AgentRun
```

On captcha or unknown fields: transition to `needs_manual`, pause automation.

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

### Q&A caching
- Hash questions with `hash_question()` before lookup
- Prefer cached `ScreeningAnswer` hits; increment `times_used`
- Only generate new answers when cache misses

## Phased checklist

### Phase 0 (foundation) ✓
- [x] Models, migrations, API, state machine
- [x] Policy config, encryption interfaces
- [x] Browser/agent interfaces

### Phase 1 (intelligence)
- [ ] Implement `DocumentGenerator` with LLM + truthfulness critic
- [ ] Implement `JobScorer` agent
- [ ] Wire `ScreeningAnswerer` to Q&A bank + optional ChromaDB
- [ ] `SourcingWorker` with cron scheduler
- [ ] Document preview endpoint

### Phase 2 (automation)
- [ ] `PlaywrightActuator` implementing `BrowserActuator`
- [ ] Session persistence to `browser_profiles/` and `SiteAccount`
- [ ] `ATSLearning` read/write on successful fills
- [ ] `needs_manual` flow for captcha

### Phase 3 (production)
- [ ] PostgreSQL, Docker Compose
- [ ] Dashboard UI
- [ ] Analytics on `AgentRun`

## Code conventions

- Type hints on all public functions
- Business logic in `services/`, not route handlers
- New models require Alembic migration
- Tests for state machine changes and schema validation

## Additional resources

- Full architecture and API details: [reference.md](reference.md)
- Project README: [README.md](../../README.md)
