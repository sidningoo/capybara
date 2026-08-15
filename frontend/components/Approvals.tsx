"use client";

import { api, fmtNum, Order, orders as ordersApi } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAction } from "@/lib/useAction";
import { Button, Chip, Empty, Panel } from "./ui";

export function Approvals({
  refreshKey,
  autonomyLevel,
  onChanged,
}: {
  refreshKey: number;
  autonomyLevel: number;
  onChanged: () => void;
}) {
  const { data, error, loading, refresh } = useApi<{ pending: Order[] }>(
    (signal) => api.approvals(signal),
    5000,
    refreshKey
  );
  const { run, pending } = useAction(() => {
    refresh();
    onChanged();
  });

  const rows = data?.pending ?? [];

  return (
    <Panel
      title="Pending Approvals"
      actions={
        rows.length > 0 ? <Chip color="amber">{rows.length} pending</Chip> : undefined
      }
    >
      {autonomyLevel >= 2 && (
        <div className="mb-2 rounded-md border border-base-700 bg-base-900/50 px-3 py-1.5 text-xs text-slate-500">
          Autonomy is L2 (full-auto): orders execute without manual approval.
        </div>
      )}
      {loading && !data ? (
        <Empty>Loading…</Empty>
      ) : error && !data ? (
        <Empty>Could not load approvals.</Empty>
      ) : rows.length === 0 ? (
        <Empty>No orders awaiting approval.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-base-700 text-left text-[11px] uppercase tracking-wider text-slate-500">
                <th className="py-2 pr-3 font-medium">Symbol</th>
                <th className="py-2 pr-3 font-medium">Side</th>
                <th className="py-2 pr-3 text-right font-medium">Qty</th>
                <th className="py-2 pr-3 font-medium">Strategy</th>
                <th className="py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr
                  key={o.client_order_id}
                  className="border-b border-base-800 last:border-0"
                >
                  <td className="py-2 pr-3 font-semibold text-slate-100">
                    {o.symbol}
                  </td>
                  <td className="py-2 pr-3">
                    <Chip color={o.side === "buy" ? "green" : "red"}>{o.side}</Chip>
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums text-slate-300">
                    {fmtNum(o.qty, 0)}
                  </td>
                  <td className="py-2 pr-3 text-slate-400">{o.strategy || "—"}</td>
                  <td className="py-2 text-right">
                    <div className="flex justify-end gap-1.5">
                      <Button
                        variant="success"
                        onClick={() =>
                          run(
                            () => ordersApi.approve(o.client_order_id),
                            `Approved ${o.symbol}`
                          )
                        }
                        disabled={pending}
                      >
                        Approve
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() =>
                          run(
                            () => ordersApi.reject(o.client_order_id),
                            `Rejected ${o.symbol}`
                          )
                        }
                        disabled={pending}
                      >
                        Reject
                      </Button>
                    </div>
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
