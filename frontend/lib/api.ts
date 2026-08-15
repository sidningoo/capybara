// Typed fetch helpers + types that mirror the Capybara FastAPI contract.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

export const TOKEN_STORAGE_KEY = "capybara_api_token";

// ───────────────────────── Types ─────────────────────────

export type EngineState =
  | "running"
  | "paused"
  | "halted"
  | "market_closed"
  | "idle"
  | string;

export interface Health {
  ok: boolean;
  service: string;
  version: string;
}

export interface Account {
  equity: number;
  cash: number;
  buying_power: number;
  currency: string;
}

export interface Position {
  symbol: string;
  qty: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
}

export interface Selection {
  strategy: string;
  regime: string;
  confidence: number;
  score: number;
  reason: string;
  sentiment: number;
  horizon: string;
}

export interface NewsSentiment {
  score: number;
  n_articles: number;
  headlines: string[];
}

export interface News {
  sentiment: Record<string, NewsSentiment>;
}

export interface Guardrails {
  day_start_equity: number;
  peak_equity: number;
  kill_switch: boolean;
  max_daily_loss_pct: number;
  max_drawdown_pct: number;
}

export interface Status {
  state: EngineState;
  autonomy_level: number;
  halt_reason: string | null;
  pinned_strategy: string | null;
  blocked_strategies: string[];
  last_cycle_at: string | null;
  universe: string[];
  account: Account | null;
  positions: Position[];
  selections: Record<string, Selection>;
  guardrails: Guardrails;
}

export interface Order {
  client_order_id: string;
  broker_order_id: string | null;
  symbol: string;
  side: "buy" | "sell" | string;
  qty: number;
  order_type: string;
  time_in_force: string;
  limit_price: number | null;
  status: string;
  filled_qty: number;
  filled_avg_price: number | null;
  strategy: string | null;
  reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface Fill {
  id: string | number;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  order_id: string;
  timestamp: string;
}

export interface EngineEvent {
  timestamp: string;
  type: string;
  data: unknown;
}

export interface Decision {
  id: string | number;
  timestamp: string;
  symbol: string;
  regime: string;
  confidence: number;
  strategy: string;
  score: number;
  reason: string;
  sentiment?: number;
  horizon?: string;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
  cash: number;
}

export interface PlaybookEntry {
  name: string;
  suited_regimes: string[];
  max_weight: number;
}

export interface Strategies {
  playbook: PlaybookEntry[];
  scores: Record<string, Record<string, number>>;
  pinned: string | null;
  blocked: string[];
}

// ───────────────────────── Token helpers ─────────────────────────

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

// ───────────────────────── Fetch core ─────────────────────────

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      return typeof detail === "string" ? detail : JSON.stringify(detail);
    }
    return JSON.stringify(body);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    cache: "no-store",
    signal,
  });
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  return (await res.json()) as T;
}

export async function apiPost<T = unknown>(
  path: string,
  body?: unknown
): Promise<T> {
  const headers: Record<string, string> = {
    "x-api-key": getToken(),
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  // Some endpoints may return empty bodies.
  const text = await res.text();
  return (text ? JSON.parse(text) : {}) as T;
}

// ───────────────────────── GET endpoints ─────────────────────────

export const api = {
  health: (signal?: AbortSignal) => apiGet<Health>("/health", signal),
  status: (signal?: AbortSignal) => apiGet<Status>("/api/status", signal),
  positions: (signal?: AbortSignal) =>
    apiGet<{ positions: Position[] }>("/api/positions", signal),
  orders: (limit = 100, status = "", signal?: AbortSignal) =>
    apiGet<{ orders: Order[] }>(
      `/api/orders?limit=${limit}${status ? `&status=${encodeURIComponent(status)}` : ""}`,
      signal
    ),
  approvals: (signal?: AbortSignal) =>
    apiGet<{ pending: Order[] }>("/api/approvals", signal),
  fills: (limit = 200, signal?: AbortSignal) =>
    apiGet<{ fills: Fill[] }>(`/api/fills?limit=${limit}`, signal),
  events: (limit = 200, signal?: AbortSignal) =>
    apiGet<{ events: EngineEvent[] }>(`/api/events?limit=${limit}`, signal),
  decisions: (limit = 200, signal?: AbortSignal) =>
    apiGet<{ decisions: Decision[] }>(`/api/decisions?limit=${limit}`, signal),
  equityCurve: (signal?: AbortSignal) =>
    apiGet<{ equity_curve: EquityPoint[] }>("/api/equity-curve", signal),
  strategies: (signal?: AbortSignal) =>
    apiGet<Strategies>("/api/strategies", signal),
  news: (signal?: AbortSignal) => apiGet<News>("/api/news", signal),
};

// ───────────────────────── POST endpoints ─────────────────────────

export const control = {
  start: () => apiPost("/api/control/start"),
  stop: () => apiPost("/api/control/stop"),
  pause: () => apiPost("/api/control/pause"),
  resume: () => apiPost("/api/control/resume"),
  clearHalt: () => apiPost("/api/control/clear-halt"),
  kill: (flatten: boolean) => apiPost("/api/control/kill", { flatten }),
  autonomy: (level: 0 | 1 | 2) => apiPost("/api/control/autonomy", { level }),
  pin: (strategy: string | null) => apiPost("/api/control/pin", { strategy }),
  block: (strategy: string, blocked: boolean) =>
    apiPost("/api/control/block", { strategy, blocked }),
};

export const orders = {
  manual: (payload: {
    symbol: string;
    side: "buy" | "sell";
    qty: number;
    reason?: string;
  }) => apiPost("/api/orders/manual", payload),
  approve: (client_order_id: string) =>
    apiPost("/api/orders/approve", { client_order_id }),
  reject: (client_order_id: string) =>
    apiPost("/api/orders/reject", { client_order_id }),
  cancel: (broker_order_id: string) =>
    apiPost(`/api/orders/cancel/${encodeURIComponent(broker_order_id)}`),
  cancelAll: () => apiPost("/api/orders/cancel-all"),
};

export const positions = {
  flatten: (symbol: string) =>
    apiPost(`/api/positions/${encodeURIComponent(symbol)}/flatten`),
  flattenAll: () => apiPost("/api/positions/flatten-all"),
};

// ───────────────────────── formatting utils ─────────────────────────

export function fmtMoney(n: number | null | undefined, currency = "USD"): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(n);
}

export function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtPct(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("en-US", { hour12: false });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", { hour12: false });
}
