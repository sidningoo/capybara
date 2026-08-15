"use client";

import { useState } from "react";
import { orders as ordersApi } from "@/lib/api";
import { useAction } from "@/lib/useAction";
import { Button, Panel } from "./ui";

export function ManualTrade({ onChanged }: { onChanged: () => void }) {
  const { run, pending } = useAction(onChanged);
  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [qty, setQty] = useState("");
  const [reason, setReason] = useState("");

  const submit = async () => {
    const sym = symbol.trim().toUpperCase();
    const q = Number(qty);
    if (!sym) return;
    if (!Number.isFinite(q) || q <= 0) return;
    const ok = await run(
      () =>
        ordersApi.manual({
          symbol: sym,
          side,
          qty: q,
          reason: reason.trim() || undefined,
        }),
      `Submitted ${side} ${q} ${sym}`
    );
    if (ok) {
      setSymbol("");
      setQty("");
      setReason("");
    }
  };

  const inputCls =
    "rounded-md border border-base-600 bg-base-900 px-2.5 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none";

  return (
    <Panel title="Manual Trade">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wider text-slate-500">
            Symbol
          </span>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="AAPL"
            className={`${inputCls} w-24 uppercase`}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wider text-slate-500">
            Side
          </span>
          <select
            value={side}
            onChange={(e) => setSide(e.target.value as "buy" | "sell")}
            className={`${inputCls} w-24`}
          >
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wider text-slate-500">
            Qty
          </span>
          <input
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            placeholder="10"
            inputMode="decimal"
            className={`${inputCls} w-24`}
          />
        </label>
        <label className="flex flex-1 flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wider text-slate-500">
            Reason (optional)
          </span>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="manual order via dashboard"
            className={`${inputCls} w-full min-w-[8rem]`}
          />
        </label>
        <Button
          type="submit"
          variant={side === "buy" ? "success" : "danger"}
          disabled={pending || !symbol.trim() || !qty}
        >
          {pending ? "Submitting…" : `Submit ${side}`}
        </Button>
      </form>
    </Panel>
  );
}
