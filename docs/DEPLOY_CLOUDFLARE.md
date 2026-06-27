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

## Recommended architectures

### Option A — API on a VPS/home server + Cloudflare Tunnel

Best when you want data and browsers on your own machine but a public HTTPS URL.

1. Run `docker compose up -d` on a VPS or home server (see root `docker-compose.yml`).
2. Install [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) and create a tunnel to `http://localhost:8000`.
3. Map a hostname (e.g. `api.example.com`) to the tunnel in the Cloudflare dashboard.
4. Enable WAF rules and optional Access policies for the dashboard/API.

Pros: full Playwright support, encrypted credentials stay on your infra.  
Cons: you operate the server; home IP uptime depends on your network.

### Option B — API on Railway / Render / Fly.io + Cloudflare in front

1. Deploy the Docker image to a platform that supports long-running Python and enough RAM for Chromium (typically **≥2 GB**).
2. Use Cloudflare as DNS/proxy in front of the platform’s hostname (orange-cloud the record).
3. Set production env vars (`SEEJOB_DATABASE_URL`, `SEEJOB_FERNET_KEY`, etc.) on the host — not in Workers.

Pros: managed compute, easier scaling.  
Cons: Playwright in containers needs extra setup; browser profiles should use persistent volumes.

### Option C — Dashboard on Cloudflare Pages, API elsewhere

1. Build the dashboard: `cd dashboard && npm run build`
2. Deploy `dashboard/dist` to **Cloudflare Pages** (static site).
3. Set `VITE_API_URL=https://api.example.com` at build time so the SPA calls your remote API.
4. Add that Pages origin to `SEEJOB_CORS_ORIGINS` on the API.

The API still runs on a Python host (Options A or B). Pages only serves the React UI.

### Option D — Single host serves both (simplest)

Build the dashboard and run `seejob` — FastAPI serves `dashboard/dist` at `/` when present. Put Cloudflare in front of that single origin (tunnel or VPS). No separate Pages project required.

## docker-compose + cloudflared (sketch)

On your VPS:

```bash
git clone <repo> && cd SeeJob
cp .env.example .env   # configure secrets
cd dashboard && npm ci && npm run build && cd ..
docker compose up -d --build
```

Install cloudflared, authenticate, and route a hostname to `http://127.0.0.1:8000`. See Cloudflare’s [tunnel docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/).

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
