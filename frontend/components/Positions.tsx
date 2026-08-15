"use client";

import { fmtMoney, fmtNum, fmtPct, positions as posApi, Status } from "@/lib/api";
import { useAction } from "@/lib/useAction";
import { Button, Empty, Panel } from "./ui";

export function Positions({
  status,
  onChanged,
}: {
  status: Status | null;
  onChanged: () => void;
}) {
  const { run, pending } = useAction(onChanged);
  const rows = status?.positions ?? [];

  return (
    <Panel
      title="Positions"
      actions={
        <Button
          variant="danger"
          onClick={() => run(() => posApi.flattenAll(), "Flattening all positions")}
          disabled={pending || rows.length === 0}
        >
          Flatten All
        </Button>
      }
    >
      {rows.length === 0 ? (
        <Empty>No open positions.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-base-700 text-left text-[11px] uppercase tracking-wider text-slate-500">
                <th className="py-2 pr-3 font-medium">Symbol</th>
                <th className="py-2 pr-3 text-right font-medium">Qty</th>
                <th className="py-2 pr-3 text-right font-medium">Avg Entry</th>
                <th className="py-2 pr-3 text-right font-medium">Current</th>
                <th className="py-2 pr-3 text-right font-medium">Mkt Value</th>
                <th className="py-2 pr-3 text-right font-medium">Unreal P&L</th>
                <th className="py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => {
                const up = p.unrealized_pl >= 0;
                return (
                  <tr
                    key={p.symbol}
                    className="border-b border-base-800 last:border-0 hover:bg-base-800/40"
                  >
                    <td className="py-2 pr-3 font-semibold text-slate-100">
                      {p.symbol}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-slate-300">
                      {fmtNum(p.qty, 0)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-slate-300">
                      {fmtMoney(p.avg_entry_price)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-slate-300">
                      {fmtMoney(p.current_price)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-slate-300">
                      {fmtMoney(p.market_value)}
                    </td>
                    <td
                      className={`py-2 pr-3 text-right tabular-nums ${
                        up ? "text-emerald-400" : "text-red-400"
                      }`}
                    >
                      {fmtMoney(p.unrealized_pl)}
                      <span className="ml-1 text-xs opacity-80">
                        ({fmtPct(p.unrealized_pl_pct)})
                      </span>
                    </td>
                    <td className="py-2 text-right">
                      <Button
                        variant="ghost"
                        onClick={() =>
                          run(
                            () => posApi.flatten(p.symbol),
                            `Flattening ${p.symbol}`
                          )
                        }
                        disabled={pending}
                      >
                        Flatten
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
