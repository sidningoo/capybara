# 🐹 Capybara — Frontend Dashboard

A dark-themed monitoring and control UI for the **Capybara** autonomous
Alpaca paper-trading bot. It talks to the Capybara FastAPI backend over REST +
a WebSocket for live updates.

Built with **Next.js 14 (App Router)**, **TypeScript**, **React 18**,
**Tailwind CSS**, and **Recharts**.

## Features

- Engine state badge + Start / Pause / Resume / Stop / Clear-Halt controls
- Prominent **Kill Switch** (with confirmation) that flattens all positions
- Autonomy level selector (L0 Approval / L1 Auto-limited / L2 Full-auto)
- Account summary with day P&L and drawdown vs. peak equity
- Live equity curve chart
- Per-symbol strategy selections (regime, confidence, score, reason)
- Strategy playbook with **Pin** / **Block** toggles, plus Pin-to-Cash / Unpin
- Positions table with per-row **Flatten** and **Flatten All**
- Pending approvals with Approve / Reject
- Manual trade form
- Orders table (status color-coded) with Cancel / Cancel-All
- Live event log combining WebSocket events with history

## Prerequisites

- Node.js 18+ (tested on Node 22)
- A running Capybara backend (FastAPI). It must run on an **always-on host** —
  see the deployment note below.

## Getting started (local)

```bash
npm install
cp .env.local.example .env.local   # then edit if your backend isn't on :8000
npm run dev
```

Open http://localhost:3000.

### Configuring the backend URL

The dashboard reads the backend base URL from the `NEXT_PUBLIC_API_BASE`
environment variable (default `http://localhost:8000`):

```bash
# .env.local
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

The WebSocket URL is derived automatically (`http` → `ws`, `https` → `wss`,
with the `/ws` path appended).

### Entering the API token

All mutating actions (start/stop, kill, pin/block, manual orders, approvals,
flatten, cancel, etc.) require an API key. `GET` requests need no auth.

1. Look at the **top-right of the header** for the `API token` input.
2. Paste the backend's API token and click **Save**.
3. The token is stored in `localStorage` under `capybara_api_token` and sent as
   the `x-api-key` header on every `POST`.

If you trigger an action without a token set, the UI will prompt you to add one.

## Production build

```bash
npm run build
npm run start
```

## Deploying to Vercel

1. Push this `frontend/` directory to a Git repo and import it into Vercel
   (Framework preset: **Next.js**).
2. In the Vercel project settings → **Environment Variables**, add:

   ```
   NEXT_PUBLIC_API_BASE = https://your-backend-host.example.com
   ```

   Use the backend's **public HTTPS URL** (this makes the WebSocket use `wss`).
3. Deploy.

> **Important:** The Python FastAPI backend runs a long-lived trading loop and
> exposes a WebSocket. It **cannot** run on Vercel (serverless/short-lived).
> Host the backend on an always-on server (a VM, container platform, Fly.io,
> Render, Railway, a Raspberry Pi, etc.) and point `NEXT_PUBLIC_API_BASE` at it.
> Make sure the backend allows CORS/WebSocket connections from your Vercel
> domain.

## Project structure

```
frontend/
├── app/
│   ├── globals.css        # Tailwind + dark theme base styles
│   ├── layout.tsx         # Root layout + toast provider
│   └── page.tsx           # Dashboard page (panel grid)
├── components/            # UI panels (Header, ControlPanel, Orders, …)
├── lib/
│   ├── api.ts             # Typed fetch helpers + contract types
│   ├── useApi.ts          # Generic polling fetch hook
│   ├── useAction.ts       # POST wrapper (token check + toasts + refresh)
│   └── useLiveStatus.ts   # WebSocket + polling status hook
├── .env.local.example
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

## How data flows

- `useLiveStatus` opens the WebSocket, seeds status from the initial
  `snapshot` frame, appends streamed events to the log, and refreshes status on
  each event. It reconnects with exponential backoff and **always** polls
  `/api/status` every 5s as a fallback.
- Each panel that owns its own list (orders, approvals, strategies, equity
  curve) uses `useApi` to poll its endpoint every 5s.
- After any successful `POST`, panels bump a shared `version` counter to force
  an immediate refresh.
