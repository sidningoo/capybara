"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, EquityPoint, fmtMoney } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Empty, Panel } from "./ui";

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color: string }>;
  label?: string | number;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border border-base-600 bg-base-900 px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-slate-400">
        {label ? new Date(label).toLocaleString("en-US", { hour12: false }) : ""}
      </div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2 tabular-nums">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: p.color }}
          />
          <span className="capitalize text-slate-400">{p.name}:</span>
          <span className="font-medium text-slate-100">{fmtMoney(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

export function EquityCurve({ refreshKey }: { refreshKey: number }) {
  const { data, error, loading } = useApi<{ equity_curve: EquityPoint[] }>(
    (signal) => api.equityCurve(signal),
    15000,
    refreshKey
  );

  const points = data?.equity_curve ?? [];

  return (
    <Panel title="Equity Curve">
      {loading && !data ? (
        <Empty>Loading…</Empty>
      ) : error && !data ? (
        <Empty>Could not load equity curve.</Empty>
      ) : points.length === 0 ? (
        <Empty>No equity history yet.</Empty>
      ) : (
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={points}
              margin={{ top: 8, right: 8, bottom: 0, left: 8 }}
            >
              <defs>
                <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#212b3b" vertical={false} />
              <XAxis
                dataKey="timestamp"
                tick={{ fill: "#64748b", fontSize: 11 }}
                tickFormatter={(t) =>
                  new Date(t).toLocaleTimeString("en-US", {
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                  })
                }
                minTickGap={40}
                stroke="#334155"
              />
              <YAxis
                tick={{ fill: "#64748b", fontSize: 11 }}
                domain={["auto", "auto"]}
                width={70}
                tickFormatter={(v) =>
                  `$${Number(v).toLocaleString("en-US", {
                    maximumFractionDigits: 0,
                  })}`
                }
                stroke="#334155"
              />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="equity"
                name="equity"
                stroke="#38bdf8"
                strokeWidth={2}
                fill="url(#equityFill)"
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}
