# SeeJob Reference Pattern Inventory

> Extracted from three open-source job-automation projects under `reference/` (gitignored).
> Archives sourced from `C:\Users\Acer\Downloads\{ApplyPilot,LangHire,StockFish}-main.zip` — all three found at exact paths.

---

## Executive Summary

| Repo | Steal this | Skip this |
|------|-----------|-----------|
| **ApplyPilot** | SQLite pipeline with stage columns; atomic job claiming; prompt-as-orchestration with `RESULT:*` codes; per-worker Chrome CDP + Playwright MCP; Gmail MCP for OTP; dry-run apply; Rich live dashboard | Full dependency on Claude Code CLI; AGPL license for direct copy |
| **LangHire** | Collect→Apply→Learn loop; per-ATS SQLite memory with domain normalization; `@@MARKER` agent output protocol; shared Playwright profile for cookies; Tauri sidecar + token-auth API; YAML job-source plugins | 100% vision/agent form fill (no deterministic fallback); LinkedIn-only collection despite plugin UI |
| **StockFish** | DOM scrape → single LLM JSON map → Playwright fill-by-selector; iframe-aware field extraction; rule-based fallback mapper; screening textarea as separate LLM call; human-in-the-loop pause before submit | Single-pass forms (no multi-page wizard loop); Node stack (SeeJob is Python) |

**Recommended hybrid for SeeJob:** Use StockFish's deterministic scrape-map-fill as the **default actuator** (`BrowserActuator`), LangHire's **per-ATS memory + Q&A bank** for repeat visits, and ApplyPilot's **pipeline orchestration, job queue, and RESULT-code failure taxonomy** for worker coordination and observability. Escalate to agent/MCP mode only when deterministic fill fails (`NEEDS_MANUAL` → agent retry).

---

## ApplyPilot Patterns

**Path:** `reference/ApplyPilot-main/`  
**Stack:** Python 3.11+, Typer CLI, SQLite (WAL), Gemini/OpenAI LLM, Claude Code + Playwright MCP + Gmail MCP for apply.

### Pipeline Stages

```
DISCOVER → ENRICH → SCORE → TAILOR → COVER → PDF → AUTO-APPLY
```

| Stage | Module | Notes |
|-------|--------|-------|
| discover | `discovery/jobspy.py`, `workday.py`, `smartextract.py` | JobSpy boards + Workday employers + direct career sites |
| enrich | `enrichment/detail.py` | JSON-LD → CSS → LLM cascade for full JD |
| score | `scoring/scorer.py` | LLM fit score 1–10 |
| tailor | `scoring/tailor.py` | Per-job resume rewrite with fabrication validator |
| cover | `scoring/cover_letter.py` | Per-job cover letter |
| pdf | `scoring/pdf.py` | Playwright headless PDF render |
| apply | `apply/launcher.py`, `apply/prompt.py` | Claude agent via MCP (separate CLI command) |

**Orchestration:** `pipeline.py` runs stages 1–5 sequentially or in **streaming mode** (`--stream`) where stages poll SQLite every 10s as a conveyor belt. Apply is always `applypilot apply`.

**Job selection for apply** (`launcher.acquire_job`):
- Requires tailored resume, `fit_score >= 7`, attempts < 3
- `BEGIN IMMEDIATE` transaction sets `apply_status = in_progress` + `agent_id`
- Manual ATS domains pre-marked `manual`; blocked SSO patterns skipped

### Playwright MCP

Python does **not** drive the browser during apply. Per worker:

1. Launch isolated Chrome with CDP on port `9222 + worker_id`
2. Write `~/.applypilot/.mcp-apply-{N}.json`:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest", "--cdp-endpoint=http://localhost:9222", "--viewport-size=1280x900"]
    },
    "gmail": {
      "command": "npx",
      "args": ["-y", "@gongrzhe/server-gmail-autoauth-mcp"]
    }
  }
}
```

3. Invoke `claude -p --mcp-config {path} --permission-mode bypassPermissions` with prompt on stdin
4. Parse `stream-json` stdout for tool actions and `RESULT:*` terminal codes

**Prompt-driven tools:** `browser_navigate`, `browser_snapshot`, `browser_fill_form`, `browser_click`, `browser_file_upload`, `browser_evaluate` (CapSolver CAPTCHA), `search_emails` / `read_email` (OTP).

### Parallel Workers

| Pool | Command | Isolation |
|------|---------|-----------|
| Pipeline | `applypilot run -w N` | ThreadPoolExecutor; thread-local Playwright + SQLite WAL |
| Apply | `applypilot apply -w N` | Per-worker CDP port, Chrome profile clone, wiped apply dir, MCP config |

Apply workers use `ThreadPoolExecutor` with `worker_loop`; limit distributed as `effective_limit // workers`. Continuous mode (`limit=0`) polls DB every 60s.

### Dry-Run

| Command | Behavior |
|---------|----------|
| `applypilot run --dry-run` | Prints stages only; no execution |
| `applypilot apply --dry-run` | **Full agent run** but prompt says do NOT click Submit; still fills and uploads |

Debug: `applypilot apply --gen --url URL` writes prompt file without running.

### Auth / OTP

- Profile `personal.password` injected into prompt for employer login
- Gmail MCP for email verification codes (step 5f in prompt)
- SSO blocklist in `config/sites.yaml` → `RESULT:FAILED:sso_required`
- Chrome profile cloning preserves cookies across runs (`apply/chrome.py`)

### Key Files

| File | Purpose |
|------|---------|
| `src/applypilot/cli.py` | All CLI commands |
| `src/applypilot/pipeline.py` | Stages 1–5 orchestration |
| `src/applypilot/database.py` | SQLite schema, migrations |
| `src/applypilot/apply/launcher.py` | Apply orchestration, MCP config, job queue |
| `src/applypilot/apply/prompt.py` | Form-filling agent prompt + RESULT codes |
| `src/applypilot/apply/chrome.py` | Chrome CDP lifecycle |
| `src/applypilot/apply/dashboard.py` | Rich live terminal dashboard |
| `src/applypilot/config/sites.yaml` | Blocked SSO, manual ATS registry |

---

## LangHire Patterns

**Path:** `reference/LangHire-main/`  
**Stack:** Tauri v2 + React 19 + FastAPI sidecar + browser-use + Playwright Chromium.

### Collect → Apply → Learn

```
Collect                          Apply                           Learn
───────                          ─────                           ─────
Agent browses job source    →    claim_job (atomic)         →    @@LEARNING markers
@@JOB_FOUND markers              build_memory_context()          extract_learnings_via_llm()
jobs.json (pending)              browser-use Agent fills           SQLite MemoryStore
@@JOB_DESCRIPTION phase 2        @@QUESTION / @@JOB_APPLIED        Q&A repo + MetricsStore
```

**Collect:** `cli/collect_jobs.py` — LinkedIn search, agent emits structured markers parsed from memory field. API: `POST /jobs/collect` in background thread with log polling.

**Apply:** `cli/apply_jobs.py` — asyncio worker pool, one `BrowserSession` per job, max 70 steps, loop detection. Modes: Easy Apply vs external ATS (different prompt blocks).

**Learn:** Post-run dual extraction — marker-based (`@@LEARNING` JSON) + LLM summary of last 30 steps. Confidence 0.85 on success, 0.5 on failure. Injected back via `format_for_prompt()` on next visit.

### Per-ATS Memory

**Core:** `backend/memory/store.py`

| Concept | Implementation |
|---------|----------------|
| Categories | `navigation`, `form_strategy`, `element_interaction`, `failure_recovery`, `site_structure`, `qa_pattern` |
| Domain normalization | `goodyear.wd1.myworkdayjobs.com` → `myworkdayjobs.com` |
| ATS detection | 30+ platforms (`ATS_DOMAINS`) |
| Transfer learning | Retrieve by normalized domain **and** `ats_platform` |
| Dedup | SHA256 content hash; duplicates bump confidence +0.05 |
| Q&A bank | Separate table; 85% token overlap fuzzy merge |

**Injection:** `build_memory_context()` in `backend/core/shared_config.py` composes profile + country hints + Q&A + domain memories → `extend_system_message` on browser-use Agent.

### Desktop UI

- Tauri spawns `langhire-backend` PyInstaller sidecar on `:8743`
- React pages: Dashboard, Jobs (Collect / Review & Apply / History tabs), Memory, Q&A, Settings
- Polling every 2s for `/jobs/collect/status` and `/apply/status` (no WebSockets)
- Bearer token auth: `secrets.token_hex(32)` in `{data_dir}/.api_token`
- Setup wizard gates on LLM config + resume + LinkedIn cookie check

### Auth / OTP

| Mechanism | Detail |
|-----------|--------|
| Platform login | `POST /auth/login/{linkedin\|gmail}` opens persistent Playwright context |
| Cookie check | `li_at` (LinkedIn), `SID`/`SSID`/`HSID` (Gmail) |
| OTP | Prompt-driven: open Gmail tab, find verification email, copy code — not a dedicated OTP service |
| Sensitive data | `agent_sensitive_data` with `<secret>email</secret>` placeholders in prompts |

### Key Files

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI server, collect/apply threads |
| `backend/memory/store.py` | SQLite memory + Q&A |
| `backend/memory/extractors.py` | Post-run learning extraction |
| `backend/core/shared_config.py` | `claim_job`, `build_memory_context` |
| `cli/apply_jobs.py` | Apply worker pool + learning |
| `cli/collect_jobs.py` | Job collection agent |
| `src/pages/Jobs.tsx` | Collect/Apply/History workflow UI |
| `backend/sources/plugins/*.yaml` | Job source plugin definitions |

---

## StockFish Patterns

**Path:** `reference/StockFish-main/`  
**Stack:** Node.js engine + Playwright + OpenAI SDK (OpenRouter/OpenAI) + React dashboard over WebSocket.

### Architecture

```
React Dashboard ←WebSocket :8765→ Node Engine (pipeline.js)
                                      ↓
                              Playwright + LLM mapper
                                      ↓
                              SQLite profile + JSON queue
```

Hackathon project built around **scrape-once, map-once, fill-once** — not multi-page wizard loops.

### Form Scrape + Single LLM Fill (Detailed)

#### Pipeline states (`src/engine/pipeline.js`)

```
INITIALIZING → NAVIGATING → ANALYZING → MAPPING → SCREENING → FILLING → SUBMITTING → PAUSED/COMPLETED
```

#### 1. DOM Extraction (`src/engine/domReducer.js`)

- `page.evaluate()` scans `input`, `select`, `textarea`
- **Skips:** hidden elements, bounding box < 2×2px, newsletter/cookie/report modals
- **Per-field descriptor:** tag, type, name, id, placeholder, ariaLabel, required, label, options, currentValue, **selector**
- **Selector priority:** `#id` → `tag[name="..."]` → nth-child path fallback
- **Iframe handling:** if main page has 0 fields, scan `page.frames()` and use frame with most fields

**LLM text format:**

```
FORM FIELDS DETECTED:

[1] <input> | type="email" | label="Email" | name="email" | [REQUIRED] | selector="#email"
[2] <select> | label="Country" | selector="select[name='country']"
    Options: "Germany" (value: DE), "United States" (value: US)
```

#### 2. LLM Prompt Shape (`src/engine/llmMapper.js`)

**One chat completion** maps all standard fields:

| Role | Content |
|------|---------|
| System | Precise form-filling assistant. Output **only** flat JSON `{ "cssSelector": "value" }`. Rules: select values match option values; checkboxes `"true"`/`"false"`; dates ISO `YYYY-MM-DD`; omit unmappable and file fields |
| User | Minimized DOM text + pretty-printed `userProfile` JSON |

**API params:** `temperature: 0.1`, `response_format: { type: 'json_object' }`

**Screening textareas** (separate call per qualifying textarea with label > 10 chars):
- System: first-person, <150 words, tailored to company/role
- User: company, role, JD excerpt, cover letter, question text, full profile
- `temperature: 0.7`, `max_tokens: 300`

**Fallback:** `ruleBasedMapper.js` on OpenRouter privacy/guardrail errors — regex keyword matching for name/email/phone/linkedin.

#### 3. Fill Strategy (`src/engine/formFiller.js`)

Flat `mapping: { cssSelector: value }` loop:

| Type | Action |
|------|--------|
| `select` | `selectOption(value)`; fallback `selectOption({ label })` |
| `textarea` | click → clear → `fill(value)` |
| text inputs | click → clear → `fill(String(value))` |
| `checkbox` | `check`/`uncheck` for `"true"` |
| `radio` | `check` |
| `file` | **Excluded from LLM**; heuristic upload by label context (`resume`/`cv`/`cover`) |
| unmapped files | `uploadUnmappedFileInputs()` sweeps remaining `input[type="file"]` |

150ms delay between fields. Uses `formContext` (page or iframe) from `reduceDOM`.

**Submit:** `submitForm.js` tries `button[type="submit"]`, `input[type="submit"]`, or text matching Submit/Apply.

**Human-in-the-loop:** Default pauses after fill (`VERIFICATION_REQUIRED`) unless `AUTO_SUBMIT=true`. Dashboard `RESUME_EXECUTION` continues.

**Dry run:** `dryRun: true` runs analyze + map only, no fill.

### Other Notable Patterns

- Pre-fill document pipeline: `documentTailor.js` generates per-job PDFs before apply
- Agent scheduler: discover APIs (Remotive, Arbeitnow, RemoteOK) → tailor → apply queue
- Telegram bot for notifications and remote control
- Live browser preview screenshots over WebSocket

### Key Files

| File | Purpose |
|------|---------|
| `src/engine/domReducer.js` | DOM scrape + minimize + iframe detection |
| `src/engine/llmMapper.js` | System/user prompts, mapping LLM call |
| `src/engine/formFiller.js` | Playwright fill execution |
| `src/engine/ruleBasedMapper.js` | Non-LLM fallback |
| `src/engine/pipeline.js` | State machine orchestrator |
| `src/engine/applyPageNavigator.js` | Job board → ATS navigation |
| `src/engine/agentScheduler.js` | Autonomous queue processor |
| `src/frontend/src/components/intervention/BlockerModal.tsx` | Human intervention UI |

---

## Recommended SeeJob Adaptations

Mapped to SeeJob's existing interfaces and application state machine.

### Phase 1 — Sourcing, Scoring, Document Generation

| Pattern source | SeeJob target | Adaptation |
|----------------|---------------|------------|
| ApplyPilot `discovery/` + `enrichment/` | `workers/base.py` sourcing worker | JobSpy + Playwright enrich with JSON-LD → CSS → LLM cascade |
| ApplyPilot `scoring/scorer.py` + `tailor.py` + `validator.py` | `agents/interfaces.py` `JobScorer`, `DocumentGenerator` | Profile-driven prompts; `TruthfulnessConstraint` mirrors banned-words/fabrication checks |
| LangHire `backend/resume/tailor.py` | Document generation service | Per-job PDF tailoring via LLM + PyMuPDF |
| ApplyPilot `pipeline.py` streaming mode | Orchestrator | Poll DB between stages; don't block enrich on full discover batch |
| LangHire `claim_job()` + FileLock | Application state machine | Atomic `pending → in_progress` before worker starts |

### Phase 2 — Browser Actuator (Form Fill)

| Pattern source | SeeJob target | Adaptation |
|----------------|---------------|------------|
| StockFish `domReducer.js` | `browser/interfaces.py` `detect_form_fields()` | Port logic to Python Playwright; return `FormField` dataclass list |
| StockFish `llmMapper.js` | New `FieldMapper` service | Single LLM call: DOM text + profile JSON → `dict[selector, value]` |
| StockFish `formFiller.js` | `BrowserActuator.fill_fields()` | Type-specific fill; 150ms inter-field delay; iframe context |
| StockFish `ruleBasedMapper.js` | Fallback in `FieldMapper` | Use when LLM unavailable or low confidence |
| LangHire `build_memory_context()` | Inject into mapper prompt | Per-ATS memories as hints for ambiguous fields |
| ApplyPilot `apply/prompt.py` RESULT codes | `BrowserActionResult` enum | Map `CAPTCHA`, `AUTH_REQUIRED`, `NEEDS_MANUAL`, `FAILED` consistently |
| ApplyPilot dry-run apply | Approval gate before `submit_form()` | Fill + screenshot + pause; user approves submit |

### Phase 3 — Learning & Memory

| Pattern source | SeeJob target | Adaptation |
|----------------|---------------|------------|
| LangHire `memory/store.py` | New `AtsMemoryStore` (SQLite) | Domain normalization + ATS platform transfer |
| LangHire `@@MARKER` protocol | Agent logging | Structured markers in agent output for Q&A extraction |
| LangHire Q&A repo | `seejob/models/screening.py` + `ScreeningAnswerer` | Fuzzy merge cached answers before LLM call |
| LangHire `metrics.py` | Observability | Track memories injected vs success rate |

### Phase 4 — Dashboard & Ops

| Pattern source | SeeJob target | Adaptation |
|----------------|---------------|------------|
| LangHire Jobs page (3-tab workflow) | API + future UI | Collect → Review → History with status polling |
| ApplyPilot `dashboard.py` | Worker observability | Per-worker status, cost, last tool action from structured logs |
| StockFish WebSocket events | Real-time apply progress | `BROWSER_PREVIEW`, `AGENT_BLOCKED` for human intervention |
| LangHire bearer token middleware | `seejob/core/security.py` | Local API token for desktop/sidecar auth |

### Escalation Strategy (Hybrid)

```
1. StockFish deterministic scrape-map-fill (fast, cheap, auditable)
2. On failure → inject LangHire per-ATS memory, retry once
3. On second failure → escalate to agent mode (ApplyPilot MCP pattern or browser-use)
4. On auth/OTP → AUTH_REQUIRED state; Gmail integration or manual takeover
5. On CAPTCHA/SSO → NEEDS_MANUAL with screenshot
```

---

## Code Snippets / Paths Worth Porting

### Highest priority

| Source path | Port to SeeJob | Why |
|-------------|----------------|-----|
| `reference/StockFish-main/src/engine/domReducer.js` | `seejob/browser/dom_reducer.py` | Direct fit for `FormField` detection; iframe-aware |
| `reference/StockFish-main/src/engine/llmMapper.js` | `seejob/browser/field_mapper.py` | Single-call mapping; screening answer generator |
| `reference/StockFish-main/src/engine/formFiller.js` | `seejob/browser/playwright_actuator.py` | Type-specific fill + file heuristics |
| `reference/LangHire-main/backend/memory/store.py` | `seejob/services/ats_memory.py` | Per-ATS procedural memory |
| `reference/LangHire-main/backend/core/shared_config.py` | `seejob/services/memory_context.py` | `build_memory_context()` pattern |
| `reference/ApplyPilot-main/src/applypilot/apply/launcher.py` | `seejob/workers/apply_worker.py` | Atomic job claim, per-worker isolation |
| `reference/ApplyPilot-main/src/applypilot/apply/prompt.py` | `seejob/agents/apply_prompt.py` | RESULT code taxonomy, CAPTCHA/SSO handling |
| `reference/ApplyPilot-main/src/applypilot/database.py` | `seejob/core/database.py` | Stage-column job queries, `ensure_columns()` migrations |

### Secondary

| Source path | Port to SeeJob | Why |
|-------------|----------------|-----|
| `reference/ApplyPilot-main/src/applypilot/enrichment/detail.py` | Sourcing enrich step | JSON-LD → CSS → LLM cascade |
| `reference/ApplyPilot-main/src/applypilot/scoring/validator.py` | Document critique | Banned words, fabrication watchlist |
| `reference/ApplyPilot-main/src/applypilot/config/sites.yaml` | `seejob/services/policy.py` | Blocked SSO, manual ATS registry |
| `reference/LangHire-main/cli/apply_jobs.py` | Apply worker | Marker parsing, learning hooks |
| `reference/LangHire-main/backend/sources/registry.py` | Job source plugins | YAML-driven source definitions |
| `reference/StockFish-main/src/engine/ruleBasedMapper.js` | Fallback mapper | LLM outage resilience |
| `reference/StockFish-main/src/engine/pipeline.js` | Apply orchestrator | State machine for fill pipeline |

### Reference only (different stack / license)

| Source path | Notes |
|-------------|-------|
| `reference/LangHire-main/src-tauri/` | Tauri shell — SeeJob may use FastAPI-only or different desktop wrapper |
| `reference/ApplyPilot-main/src/applypilot/apply/chrome.py` | Chrome CDP flags — useful if adopting MCP apply path |
| `reference/StockFish-main/src/engine/telegramBot.js` | Optional notification channel |

---

## Appendix: Archive Provenance

| Archive | Found at | Extracted to |
|---------|----------|--------------|
| ApplyPilot-main.zip | `C:\Users\Acer\Downloads\ApplyPilot-main.zip` | `reference/ApplyPilot-main/` |
| LangHire-main.zip | `C:\Users\Acer\Downloads\LangHire-main.zip` | `reference/LangHire-main/` |
| StockFish-main.zip | `C:\Users\Acer\Downloads\StockFish-main.zip` | `reference/StockFish-main/` |

The `reference/` directory is gitignored (`reference/*` with `!reference/.gitkeep`). Do not commit extracted repo contents.
