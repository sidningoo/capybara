"use client";

import { Analytics, api, fmtMoney, fmtNum, fmtPct } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Empty, Panel } from "./ui";

// Render a profit factor which may be null (no losses yet → "∞") or missing.
function fmtProfitFactor(pf: number | null | undefined): string {
  if (pf === null || pf === undefined) return "—";
  if (!Number.isFinite(pf)) return "∞";
  return fmtNum(pf, 2);
}

function Metric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
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
      <div className={`mt-1 text-lg font-semibold tabular-nums ${color}`}>
        {value}
      </div>
    </div>
  );
}

function toneFor(n: number): "profit" | "loss" {
  return n >= 0 ? "profit" : "loss";
}

export function AnalyticsPanel({ refreshKey }: { refreshKey?: number }) {
  const { data, error, loading } = useApi<Analytics>(
    (signal) => api.analytics(signal),
    10000,
    refreshKey ?? 0
  );

  const perStrategy = data ? Object.entries(data.per_strategy) : [];

  return (
    <Panel title="Performance Analytics">
      {loading && !data ? (
        <Empty>Loading…</Empty>
      ) : error && !data ? (
        <Empty>Could not load analytics.</Empty>
      ) : !data ? (
        <Empty>No analytics available.</Empty>
      ) : (
        <div className="flex flex-col gap-4">
          {/* Plain-English summary, prominent. */}
          <p className="text-base leading-relaxed text-slate-200">
            {data.summary}
          </p>

          {/* Compact metrics grid. */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric
              label="Total Return"
              value={fmtPct(data.total_return_pct)}
              tone={toneFor(data.total_return_pct)}
            />
            <Metric
              label="Max Drawdown"
              value={fmtPct(data.max_drawdown_pct)}
              tone={data.max_drawdown_pct < 0 ? "loss" : "neutral"}
            />
            <Metric label="Sharpe" value={fmtNum(data.sharpe, 2)} />
            <Metric label="Win Rate" value={fmtPct(data.win_rate_pct)} />
            <Metric
              label="Profit Factor"
              value={fmtProfitFactor(data.profit_factor)}
            />
            <Metric
              label="Realized P&L"
              value={fmtMoney(data.realized_pnl)}
              tone={toneFor(data.realized_pnl)}
            />
            <Metric label="Round Trips" value={fmtNum(data.n_round_trips, 0)} />
            <Metric label="Fills" value={fmtNum(data.n_fills, 0)} />
          </div>

          {/* Per-strategy breakdown. */}
          <div>
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-slate-500">
              Per Strategy
            </div>
            {perStrategy.length === 0 ? (
              <Empty>No closed trades yet.</Empty>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-base-700 text-left text-xs uppercase tracking-wider text-slate-500">
                      <th className="py-2 pr-3 font-medium">Strategy</th>
                      <th className="py-2 pr-3 text-right font-medium">
                        Round Trips
                      </th>
                      <th className="py-2 pr-3 text-right font-medium">
                        Win Rate
                      </th>
                      <th className="py-2 pr-3 text-right font-medium">
                        Net P&L
                      </th>
                      <th className="py-2 text-right font-medium">
                        Profit Factor
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {perStrategy.map(([name, s]) => (
                      <tr
                        key={name}
                        className="border-b border-base-800 last:border-0"
                      >
                        <td className="py-2 pr-3 font-medium text-slate-100">
                          {name}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums text-slate-300">
                          {fmtNum(s.round_trips, 0)}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums text-slate-300">
                          {fmtPct(s.win_rate_pct)}
                        </td>
                        <td
                          className={`py-2 pr-3 text-right tabular-nums ${
                            s.net_pnl >= 0 ? "text-emerald-400" : "text-red-400"
                          }`}
                        >
                          {fmtMoney(s.net_pnl)}
                        </td>
                        <td className="py-2 text-right tabular-nums text-slate-300">
                          {fmtProfitFactor(s.profit_factor)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}
