# Deploying SeeJob behind Cloudflare

Honest guidance for running SeeJob with Cloudflare DNS, CDN, and WAF. SeeJob is a **Python FastAPI backend** with **Playwright browser automation** and a **React dashboard** — not a typical edge-only app.

## What Cloudflare is good for here

| Layer | Recommendation |
|-------|------------------|
| DNS | Point your domain at Cloudflare |
| CDN / caching | Static dashboard assets, health checks |
| WAF / DDoS | Protect public API hostname |
| TLS | Terminate HTTPS at Cloudflare or origin |

## What does **not** fit Cloudflare Workers alone

SeeJob’s backend needs:

- Long-running Python (FastAPI, SQLAlchemy, Alembic)
- Playwright + Chromium for ATS form fill (minutes per application, persistent browser profiles)
- Local or volume-backed storage (`generated/documents`, `browser_profiles`, SQLite/PostgreSQL)

**Cloudflare Workers are not a suitable host** for this API. Workers have CPU/time limits, no native Playwright/Chromium, and no persistent filesystem for browser sessions. Do not expect to run `seejob-tick` or Playwright automation entirely on Workers.

---

## Option A — Dashboard on Pages, API on your Windows PC (recommended for home users)

Use this when you want the **dashboard on a public URL** (phone, laptop, anywhere) while the **API and Playwright browser stay on your Windows machine**.

### Architecture

```
Browser (anywhere)
    │
    ├─► https://seejob.pages.dev          Cloudflare Pages (static React dashboard)
    │
    └─► https://api.yourdomain.com        Cloudflare Tunnel (cloudflared)
              │
              └─► http://127.0.0.1:8000   SeeJob API on your PC (seejob / Docker)
```

**Why the tunnel is required:** A browser loading the dashboard from `*.pages.dev` cannot call `http://localhost:8000` on your PC. The tunnel exposes your local API as a public HTTPS hostname that the dashboard can reach.

### Prerequisites

- Cloudflare account with a domain (or use the default `*.pages.dev` hostname for the dashboard only)
- SeeJob running locally on port `8000` (`seejob` or `docker compose up`)
- Dashboard repo connected to GitHub (for Pages)

### Step 1 — Install cloudflared on Windows

Download and install [cloudflared for Windows](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) or use winget:

```powershell
winget install --id Cloudflare.cloudflared
```

Verify:

```powershell
cloudflared --version
```

### Step 2 — Log in to Cloudflare

```powershell
cloudflared tunnel login
```

This opens a browser window. Select the zone (domain) you will use for the API hostname (e.g. `yourdomain.com`).

### Step 3 — Create a tunnel and config

Create a named tunnel:

```powershell
cloudflared tunnel create seejob-api
```

Note the tunnel UUID printed by the command. Create a config file at `%USERPROFILE%\.cloudflared\config.yml`:

```yaml
tunnel: <TUNNEL_UUID>
credentials-file: C:\Users\<You>\.cloudflared\<TUNNEL_UUID>.json

ingress:
  - hostname: api.yourdomain.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

Route DNS for the API hostname to the tunnel (Cloudflare dashboard or CLI):

```powershell
cloudflared tunnel route dns seejob-api api.yourdomain.com
```

Replace `api.yourdomain.com` with your chosen subdomain.

### Step 4 — Run the tunnel (keep it running while applying)

**Foreground (testing):**

```powershell
cloudflared tunnel run seejob-api
```

**Windows service (always on):**

```powershell
cloudflared service install
cloudflared tunnel run seejob-api
```

Or install as a Windows Service via `nssm` / Task Scheduler so it starts at login. The tunnel must be running whenever you use the public dashboard.

Confirm the API is reachable:

```powershell
curl https://api.yourdomain.com/health
```

Expected: `{"status":"ok"}` (with SeeJob running locally).

### Step 5 — Deploy dashboard to Cloudflare Pages

1. In [Cloudflare Dashboard](https://dash.cloudflare.com) → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**.
2. Select this repository.
3. Build settings:

| Setting | Value |
|---------|--------|
| Build command | `cd dashboard && npm ci && npm run build` |
| Build output directory | `dashboard/dist` |
| Root directory | `/` (repo root) |

4. Deploy. Your site will be at `https://<project>.pages.dev` (or a custom domain you attach later).

### Step 6 — Set Pages environment variable (build-time)

In Pages → your project → **Settings** → **Environment variables**, add:

| Name | Value | Environments |
|------|--------|--------------|
| `VITE_API_URL` | `https://api.yourdomain.com` | Production (and Preview if desired) |

**Important:** `VITE_*` variables are baked in at **build** time. After changing `VITE_API_URL`, trigger a **new deployment** (retry deployment or push a commit).

### Step 7 — Allow the Pages origin in API CORS

On your **local** `.env` (same machine running SeeJob), add your Pages URL to `SEEJOB_CORS_ORIGINS`:

```env
SEEJOB_CORS_ORIGINS=["https://seejob.pages.dev","https://your-custom-domain.com","http://localhost:5173"]
```

Restart the API after editing `.env`:

```powershell
# Stop and restart seejob, or:
docker compose restart api
```

Without this, the browser will block API requests from the Pages origin.

### Step 8 — Security (strongly recommended)

Exposing `:8000` via a tunnel makes your API reachable from the internet.

| Risk | Mitigation |
|------|------------|
| Unauthenticated API access | Enable [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/) on `api.yourdomain.com` (email OTP, Google login, etc.) |
| Abuse / scanning | Cloudflare WAF rules on the API hostname |
| Secrets on PC | Keep `.env`, Fernet keys, and Gmail passwords off GitHub; use strong `SEEJOB_FERNET_KEY` |

SeeJob does not ship production API key auth by default — treat the tunnel URL as sensitive until you add Access or future auth.

### What must stay running on your PC

| Process | Purpose |
|---------|---------|
| **SeeJob API** (`seejob` or `docker compose up`) | REST API, document generation, Playwright |
| **cloudflared tunnel** | Bridges `api.yourdomain.com` → `127.0.0.1:8000` |
| **`seejob-tick` (optional)** | Scheduled sourcing + pipeline queue — use Windows Task Scheduler (see root README) |

If the PC sleeps or the tunnel stops, the public dashboard will load but API calls will fail.

### Quick checklist (Option A)

- [ ] Local API healthy: `http://127.0.0.1:8000/health`
- [ ] Tunnel healthy: `https://api.yourdomain.com/health`
- [ ] Pages build with `VITE_API_URL` pointing at tunnel URL
- [ ] `SEEJOB_CORS_ORIGINS` includes Pages origin
- [ ] `SEEJOB_FERNET_KEY` set; approval gates enabled for production
- [ ] Plan for `needs_manual` captcha flows ([CAPTCHA.md](CAPTCHA.md))

---

## Other architectures

### Option B — API on a VPS/home server + Cloudflare Tunnel

Same tunnel pattern as Option A, but the API runs on a **Linux VPS or always-on home server** instead of a Windows laptop. Use `docker compose up -d` on the server (see root `docker-compose.yml`).

Pros: full Playwright support, better uptime than a laptop.  
Cons: you operate the server.

### Option C — API on Railway / Render / Fly.io + Cloudflare in front

1. Deploy the Docker image to a platform that supports long-running Python and enough RAM for Chromium (typically **≥2 GB**).
2. Use Cloudflare as DNS/proxy in front of the platform’s hostname (orange-cloud the record).
3. Set production env vars (`SEEJOB_DATABASE_URL`, `SEEJOB_FERNET_KEY`, etc.) on the host — not in Workers.

Pros: managed compute, easier scaling.  
Cons: Playwright in containers needs extra setup; browser profiles should use persistent volumes.

### Option D — Single host serves both (simplest)

Build the dashboard and run `seejob` — FastAPI serves `dashboard/dist` at `/` when present. Put Cloudflare in front of that single origin (tunnel or VPS). No separate Pages project required.

## Lovable and similar “AI app builders”

Tools like [Lovable](https://lovable.dev) can help regenerate or host a **frontend** quickly. They do **not** replace SeeJob’s Python backend, Playwright actuator, or encrypted credential store. Use them for UI experiments only; keep orchestration and browser automation on a proper Python host.

## Checklist before going live

- [ ] `SEEJOB_FERNET_KEY` and `SEEJOB_SECRET_KEY` set to strong random values
- [ ] PostgreSQL (not SQLite) for production (`docker-compose.yml` default)
- [ ] `SEEJOB_CORS_ORIGINS` includes your dashboard origin only
- [ ] Rate limits configured in `PolicyConfig`
- [ ] Approval gates enabled (`require_doc_approval`, `require_submit_approval`)
- [ ] Plan for `needs_manual` — captcha/login cannot run headless on Workers ([CAPTCHA.md](CAPTCHA.md))

## Related docs

- Root [README.md](../README.md) — Docker Compose, env vars, dashboard dev proxy
- [CAPTCHA.md](CAPTCHA.md) — captcha and manual intervention flows
