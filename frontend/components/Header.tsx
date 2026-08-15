"use client";

import { useEffect, useState } from "react";
import {
  control,
  EngineState,
  getToken,
  NotifyTestResult,
  setToken,
  Status,
} from "@/lib/api";
import { useAction } from "@/lib/useAction";
import { useToast } from "./Toaster";

export function stateColor(state: EngineState): string {
  switch (state) {
    case "running":
      return "green";
    case "paused":
      return "amber";
    case "halted":
      return "red";
    case "market_closed":
      return "slate";
    case "idle":
    default:
      return "gray";
  }
}

const AUTONOMY_LABELS: Record<number, string> = {
  0: "L0 · Approval",
  1: "L1 · Auto-limited",
  2: "L2 · Full-auto",
};

function StateBadge({ state }: { state: EngineState }) {
  const color = stateColor(state);
  const dot: Record<string, string> = {
    green: "bg-emerald-400",
    amber: "bg-amber-400",
    red: "bg-red-400",
    slate: "bg-slate-400",
    gray: "bg-gray-400",
  };
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-md border px-3 py-1 text-sm font-semibold uppercase tracking-wide ${
        color === "green"
          ? "border-emerald-700 bg-emerald-900/40 text-emerald-300"
          : color === "amber"
            ? "border-amber-700 bg-amber-900/40 text-amber-300"
            : color === "red"
              ? "border-red-700 bg-red-900/40 text-red-300"
              : "border-slate-600 bg-slate-800/60 text-slate-300"
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${dot[color]} animate-pulse`} />
      {state || "unknown"}
    </span>
  );
}

function TokenInput() {
  const [token, setTok] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setTok(getToken());
  }, []);

  const save = () => {
    setToken(token.trim());
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  return (
    <div className="flex items-center gap-1.5">
      <input
        type="password"
        value={token}
        onChange={(e) => setTok(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && save()}
        placeholder="API token"
        aria-label="API token"
        className="w-32 rounded-md border border-base-600 bg-base-900 px-2 py-1 text-sm text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
      />
      <button
        onClick={save}
        className="rounded-md border border-base-600 bg-base-700 px-2 py-1 text-xs text-slate-200 hover:bg-base-600"
      >
        {saved ? "✓" : "Save"}
      </button>
    </div>
  );
}

export function Header({
  status,
  connected,
  onChanged,
}: {
  status: Status | null;
  connected: boolean;
  onChanged: () => void;
}) {
  const { run, pending } = useAction(onChanged);
  const { push } = useToast();
  const level = status?.autonomy_level ?? 0;

  const setLevel = (lvl: 0 | 1 | 2) => {
    if (lvl === level) return;
    run(() => control.autonomy(lvl), `Autonomy set to ${AUTONOMY_LABELS[lvl]}`);
  };

  const testAlert = async () => {
    let result: NotifyTestResult | null = null;
    const ok = await run(async () => {
      result = await control.notifyTest();
    });
    if (ok && result) {
      const { enabled, channels } = result as NotifyTestResult;
      const msg =
        channels.length > 0
          ? `Notifications: ${channels.join(", ")}`
          : "No channels configured";
      push(msg, enabled ? "success" : "info");
    }
  };

  return (
    <header className="sticky top-0 z-40 border-b border-base-700 bg-base-900/80 backdrop-blur">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-slate-100">🐹 Capybara</h1>
          <span className="hidden text-xs text-slate-500 sm:inline">
            autonomous paper-trading
          </span>
        </div>

        <StateBadge state={status?.state ?? "idle"} />

        <div className="flex items-center gap-1 rounded-lg border border-base-700 bg-base-850 p-0.5">
          {([0, 1, 2] as const).map((lvl) => (
            <button
              key={lvl}
              onClick={() => setLevel(lvl)}
              disabled={pending}
              title={AUTONOMY_LABELS[lvl]}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
                level === lvl
                  ? "bg-sky-600 text-white"
                  : "text-slate-400 hover:bg-base-700 hover:text-slate-200"
              }`}
            >
              {AUTONOMY_LABELS[lvl]}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-3">
          <button
            onClick={testAlert}
            disabled={pending}
            title="Send a test notification through configured channels"
            className="rounded-md border border-base-600 bg-base-700 px-2.5 py-1 text-xs text-slate-200 transition-colors hover:bg-base-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Test alert
          </button>
          <TokenInput />
          <div className="flex items-center gap-1.5" title={connected ? "WebSocket connected" : "WebSocket disconnected"}>
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                connected ? "bg-emerald-400 shadow-[0_0_6px] shadow-emerald-400" : "bg-red-500"
              }`}
            />
            <span className="hidden text-xs text-slate-400 md:inline">
              {connected ? "live" : "offline"}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
