"use client";

import { fmtMoney, fmtPct, Status } from "@/lib/api";
import { Empty, Panel } from "./ui";

function Stat({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "profit" | "loss";
}) {
  const color =
    tone === "profit"
      ? "text-emerald-400"
      : tone === "loss"
        ? "text-red-400"
        : "text-slate-100";
  return (
    <div className="rounded-lg border border-base-700 bg-base-900/50 px-3 py-2.5">
      <div className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
        {label}
      </div>
      <div className={`mt-1 text-xl font-semibold tabular-nums ${color}`}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs tabular-nums text-slate-400">{sub}</div>}
    </div>
  );
}

export function AccountSummary({ status }: { status: Status | null }) {
  const acct = status?.account ?? null;
  const g = status?.guardrails;
  const currency = acct?.currency || "USD";

  let dayPl: number | null = null;
  let dayPlPct: number | null = null;
  if (acct && g && g.day_start_equity) {
    dayPl = acct.equity - g.day_start_equity;
    dayPlPct = (dayPl / g.day_start_equity) * 100;
  }

  let drawdown: number | null = null;
  let drawdownPct: number | null = null;
  if (acct && g && g.peak_equity) {
    drawdown = acct.equity - g.peak_equity;
    drawdownPct = (drawdown / g.peak_equity) * 100;
  }

  return (
    <Panel title="Account">
      {!acct ? (
        <Empty>No account data — broker not connected.</Empty>
      ) : (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Stat label="Equity" value={fmtMoney(acct.equity, currency)} />
          <Stat label="Cash" value={fmtMoney(acct.cash, currency)} />
          <Stat label="Buying Power" value={fmtMoney(acct.buying_power, currency)} />
          <Stat
            label="Day P&L"
            value={dayPl === null ? "—" : fmtMoney(dayPl, currency)}
            sub={dayPlPct === null ? undefined : fmtPct(dayPlPct)}
            tone={dayPl === null ? "neutral" : dayPl >= 0 ? "profit" : "loss"}
          />
          <Stat
            label="Drawdown (vs peak)"
            value={drawdown === null ? "—" : fmtMoney(drawdown, currency)}
            sub={drawdownPct === null ? undefined : fmtPct(drawdownPct)}
            tone={drawdown === null ? "neutral" : drawdown < 0 ? "loss" : "profit"}
          />
          <Stat
            label="Peak Equity"
            value={g ? fmtMoney(g.peak_equity, currency) : "—"}
            sub={g ? `start ${fmtMoney(g.day_start_equity, currency)}` : undefined}
          />
        </div>
      )}
      {g && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
          <span>Max daily loss: {g.max_daily_loss_pct}%</span>
          <span>Max drawdown: {g.max_drawdown_pct}%</span>
          <span>
            Kill switch:{" "}
            <span className={g.kill_switch ? "text-red-400" : "text-emerald-400"}>
              {g.kill_switch ? "ENGAGED" : "clear"}
            </span>
          </span>
        </div>
      )}
    </Panel>
  );
}
