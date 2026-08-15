# Capybara — Deployment

Capybara is **two deployables** because the pieces have opposite hosting needs:

```
[ Browser ] → [ Next.js dashboard on Vercel ] → HTTP/WS → [ Python engine + API on an always-on host ] → [ Alpaca paper ]
```

- **Dashboard → Vercel** (static/serverless, perfect fit).
- **Engine + API → an always-on host** (Railway / Render / Fly.io / a VM / a Raspberry Pi).
  It runs a continuous loop and holds a WebSocket, so it **cannot** run on Vercel.

---

## 1) Backend (engine + control API)

### Option A — Docker (recommended)

```bash
cd backend
cp .env.example .env          # fill in ALPACA_API_KEY/SECRET (paper) + CAPYBARA_API_TOKEN
docker build -t capybara-backend .
docker run -p 8000:8000 --env-file .env -v capybara-data:/data capybara-backend
```

Or from the repo root with compose:

```bash
docker compose up backend                 # engine + API on :8000
docker compose --profile full up           # + dashboard on :3000 (local all-in-one)
```

The SQLite state/audit DB is persisted in the `capybara-data` volume (`/data`).

### Option B — Buildpack platform (Railway / Render / Heroku)

- Set the service **root directory** to `backend/`.
- It uses `backend/Procfile` (`web: capybara run`).
- Set the environment variables from `.env.example` in the platform dashboard.
- Ensure the platform exposes the port from `CAPYBARA_API_PORT` (default 8000) and does
  **not** sleep the service (it must stay always-on).

### Option C — Fly.io / a VM / systemd

`pip install .` then run `capybara run` under a process manager (systemd, supervisor,
pm2, tmux). Point a reverse proxy (Caddy/Nginx) at port 8000 for HTTPS + WSS.

### Required environment

At minimum: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` (paper), and a strong
`CAPYBARA_API_TOKEN`. Set `CAPYBARA_CORS_ORIGINS` to your dashboard's URL. See
`backend/.env.example` for the full list (autonomy, risk, sentiment, notifications).

Generate an API token:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 2) Frontend (dashboard → Vercel)

1. Import the repo into Vercel; set the **Root Directory** to `frontend/`.
2. Add env var `NEXT_PUBLIC_API_BASE = https://your-backend-host.example.com`
   (the backend's public **HTTPS** URL — this makes the dashboard use `wss` for the
   live feed).
3. Deploy. Open the app, paste your `CAPYBARA_API_TOKEN` into the header input to
   enable controls.

---

## 3) CORS & security checklist

- Set `CAPYBARA_CORS_ORIGINS` on the backend to your exact Vercel domain(s),
  comma-separated. The WebSocket and REST both rely on this.
- Keep `ALPACA_PAPER=True`. Live trading is intentionally unsupported.
- Never commit `.env`. Only `.env.example` is tracked.
- The API token guards every mutating endpoint (`x-api-key`). Rotate it if leaked.
- Optional: put the backend behind HTTPS (a reverse proxy or the platform's TLS) so
  the browser can use `wss://` for the live event stream.

---

## 4) Health & operations

- `GET /health` returns a liveness JSON (used by the Docker healthcheck).
- The engine reconciles against the broker on startup and periodically, so restarts
  are safe (broker = source of truth).
- Enable **notifications** (`CAPYBARA_ENABLE_NOTIFICATIONS=True` + a webhook/SMTP) to
  be alerted on halts / approvals and to receive the daily digest — so a hosted,
  hands-off deployment tells you when it needs a look.
