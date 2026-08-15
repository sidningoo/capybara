"use client";

import {
  api,
  fmtNum,
  fmtTime,
  Order,
  orders as ordersApi,
} from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAction } from "@/lib/useAction";
import { Button, Chip, Empty, Panel } from "./ui";

const OPEN_STATUSES = new Set([
  "new",
  "accepted",
  "pending_new",
  "partially_filled",
  "pending_approval",
  "held",
  "open",
]);

function statusColor(status: string): string {
  const s = status.toLowerCase();
  if (s === "filled") return "green";
  if (s.includes("cancel") || s === "rejected" || s === "expired") return "red";
  if (s === "partially_filled") return "amber";
  if (s === "pending_approval") return "violet";
  if (OPEN_STATUSES.has(s)) return "sky";
  return "slate";
}

export function Orders({
  refreshKey,
  onChanged,
}: {
  refreshKey: number;
  onChanged: () => void;
}) {
  const { data, error, loading, refresh } = useApi<{ orders: Order[] }>(
    (signal) => api.orders(100, "", signal),
    5000,
    refreshKey
  );
  const { run, pending } = useAction(() => {
    refresh();
    onChanged();
  });

  const rows = data?.orders ?? [];
  const hasOpen = rows.some((o) => OPEN_STATUSES.has(o.status.toLowerCase()));

  return (
    <Panel
      title="Orders"
      actions={
        <Button
          variant="ghost"
          onClick={() => run(() => ordersApi.cancelAll(), "Cancelling all open orders")}
          disabled={pending || !hasOpen}
        >
          Cancel All
        </Button>
      }
    >
      {loading && !data ? (
        <Empty>Loading…</Empty>
      ) : error && !data ? (
        <Empty>Could not load orders.</Empty>
      ) : rows.length === 0 ? (
        <Empty>No orders yet.</Empty>
      ) : (
        <div className="max-h-96 overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-base-850">
              <tr className="border-b border-base-700 text-left text-[11px] uppercase tracking-wider text-slate-500">
                <th className="py-2 pr-3 font-medium">Time</th>
                <th className="py-2 pr-3 font-medium">Symbol</th>
                <th className="py-2 pr-3 font-medium">Side</th>
                <th className="py-2 pr-3 text-right font-medium">Qty</th>
                <th className="py-2 pr-3 text-right font-medium">Filled</th>
                <th className="py-2 pr-3 font-medium">Type</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => {
                const open = OPEN_STATUSES.has(o.status.toLowerCase());
                return (
                  <tr
                    key={o.client_order_id}
                    className="border-b border-base-800 last:border-0 hover:bg-base-800/40"
                  >
                    <td className="py-2 pr-3 tabular-nums text-slate-400">
                      {fmtTime(o.created_at)}
                    </td>
                    <td className="py-2 pr-3 font-semibold text-slate-100">
                      {o.symbol}
                    </td>
                    <td className="py-2 pr-3">
                      <Chip color={o.side === "buy" ? "green" : "red"}>{o.side}</Chip>
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-slate-300">
                      {fmtNum(o.qty, 0)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-slate-400">
                      {fmtNum(o.filled_qty, 0)}
                    </td>
                    <td className="py-2 pr-3 text-slate-400">{o.order_type}</td>
                    <td className="py-2 pr-3">
                      <Chip color={statusColor(o.status)}>{o.status}</Chip>
                    </td>
                    <td className="py-2 text-right">
                      {open && o.broker_order_id ? (
                        <Button
                          variant="ghost"
                          onClick={() =>
                            run(
                              () => ordersApi.cancel(o.broker_order_id as string),
                              `Cancelling ${o.symbol}`
                            )
                          }
                          disabled={pending}
                        >
                          Cancel
                        </Button>
                      ) : null}
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
