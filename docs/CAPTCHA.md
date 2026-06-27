# Captcha handling in SeeJob

SeeJob encounters captchas and bot checks during ATS login and apply flows. This document summarizes practical options — not a recommendation to bypass site terms of service.

## Default: human-in-the-loop

SeeJob’s intended path when automation is blocked:

1. The pipeline sets the application to **`needs_manual`** (or **`auth_required`** for login).
2. The dashboard shows the interrupt; you complete captcha/login in a real browser session.
3. Resume with `POST /api/v1/applications/{id}/resume`, or provide OTP via `POST /api/v1/applications/{id}/provide-otp`.

This is the **default and most reliable** approach. It avoids ToS risk, works on every ATS, and needs no third-party solver budget.

## Paid commercial solvers

### CapSolver (integrated)

When `SEEJOB_CAPSOLVER_API_KEY` is set, SeeJob can attempt automatic solve for supported types (e.g. reCAPTCHA, Turnstile) via `seejob/integrations/capsolver.py`.

- **Pros:** Works unattended for supported captcha types.
- **Cons:** Paid per solve; not 100% success; some sites block solver traffic.

There is **no reliable, fully free commercial captcha API** suitable for production job-application volume. Free tiers are rate-limited, ephemeral, or low quality.

### Other paid services (2Captcha, Anti-Captcha, etc.)

Same tradeoffs as CapSolver. SeeJob does not ship integrations for every vendor; CapSolver is the supported optional integration today.

## Why we do not integrate “free captcha breaker” repos

Open-source or sketchy captcha-breaking projects often:

- Violate target site terms of service
- Break when sites rotate challenges (constant maintenance)
- Require GPU farms or ML models that are fragile in CI/production
- Pose security/legal risk when handling credentials next to untrusted code

SeeJob **does not** integrate random GitHub captcha-cracking libraries. Prefer **`needs_manual`** and optional CapSolver instead.

## Playwright “stealth” and manual solve

Playwright can reduce obvious automation signals (realistic viewport, persisted profiles under `SEEJOB_BROWSER_PROFILES_DIR`, human-like delays). That helps **legitimate** automation on sites that allow it — it is not a captcha guarantee.

When a captcha appears:

- Let the run pause in `needs_manual`
- Open the linked apply URL in your browser (or use the persisted profile session)
- Solve the challenge, then resume from the dashboard

## OTP without Gmail

Captcha and OTP are separate concerns. Gmail IMAP (`GMAIL_USER` / `GMAIL_APP_PASSWORD`) is **optional** — only for automatic OTP fetch. You can always paste OTPs through the dashboard API instead.

## Summary

| Approach | Cost | Reliability | Recommended |
|----------|------|-------------|-------------|
| Dashboard manual / `needs_manual` | Free | High | **Yes — default** |
| CapSolver (`SEEJOB_CAPSOLVER_API_KEY`) | Paid | Medium | Optional |
| Other commercial APIs | Paid | Medium | BYO integration |
| Self-hosted / “free breaker” repos | Hidden cost | Low | **No** |
| Playwright stealth alone | Free | Low for captchas | Supplement only |

For deployment constraints (e.g. Cloudflare Workers cannot run Playwright), see [DEPLOY_CLOUDFLARE.md](DEPLOY_CLOUDFLARE.md).
