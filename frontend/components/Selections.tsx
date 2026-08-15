"use client";

import { fmtNum, Status } from "@/lib/api";
import {
  Chip,
  ConfidenceBar,
  Empty,
  HorizonChip,
  Panel,
  regimeColor,
  SentimentBar,
} from "./ui";

export function Selections({ status }: { status: Status | null }) {
  const selections = status?.selections ?? {};
  const rows = Object.entries(selections).sort(([a], [b]) => a.localeCompare(b));

  return (
    <Panel title="Strategy Selections">
      {rows.length === 0 ? (
        <Empty>No active selections.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-base-700 text-left text-[11px] uppercase tracking-wider text-slate-500">
                <th className="py-2 pr-3 font-medium">Symbol</th>
                <th className="py-2 pr-3 font-medium">Regime</th>
                <th className="py-2 pr-3 font-medium">Strategy</th>
                <th className="py-2 pr-3 font-medium">Confidence</th>
                <th className="py-2 pr-3 font-medium">Score</th>
                <th className="py-2 pr-3 font-medium">Sentiment</th>
                <th className="py-2 pr-3 font-medium">Horizon</th>
                <th className="py-2 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([symbol, sel]) => (
                <tr
                  key={symbol}
                  className="border-b border-base-800 last:border-0 hover:bg-base-800/40"
                >
                  <td className="py-2 pr-3 font-semibold text-slate-100">
                    {symbol}
                  </td>
                  <td className="py-2 pr-3">
                    <Chip color={regimeColor(sel.regime)}>{sel.regime}</Chip>
                  </td>
                  <td className="py-2 pr-3 text-slate-300">{sel.strategy}</td>
                  <td className="py-2 pr-3">
                    <ConfidenceBar value={sel.confidence} />
                  </td>
                  <td className="py-2 pr-3 tabular-nums text-slate-300">
                    {fmtNum(sel.score, 3)}
                  </td>
                  <td className="py-2 pr-3">
                    <SentimentBar score={sel.sentiment ?? 0} />
                  </td>
                  <td className="py-2 pr-3">
                    <HorizonChip horizon={sel.horizon} />
                  </td>
                  <td className="max-w-xs truncate py-2 text-slate-400" title={sel.reason}>
                    {sel.reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
