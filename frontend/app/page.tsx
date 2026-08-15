"use client";

import { API_BASE, fmtDateTime } from "@/lib/api";
import { useLiveStatus } from "@/lib/useLiveStatus";
import { AccountSummary } from "@/components/AccountSummary";
import { Approvals } from "@/components/Approvals";
import { ControlPanel } from "@/components/ControlPanel";
import { EquityCurve } from "@/components/EquityCurve";
import { EventLog } from "@/components/EventLog";
import { Header } from "@/components/Header";
import { ManualTrade } from "@/components/ManualTrade";
import { NewsPanel } from "@/components/NewsPanel";
import { Orders } from "@/components/Orders";
import { Positions } from "@/components/Positions";
import { Selections } from "@/components/Selections";
import { StrategiesPanel } from "@/components/StrategiesPanel";

export default function Page() {
  const { status, statusError, connected, events, version, refresh } =
    useLiveStatus(5000);

  // Backend considered down only when we have never received status AND the
  // last poll errored. This avoids flapping the banner between polls.
  const backendDown = statusError !== null && status === null;

  return (
    <main className="min-h-screen">
      <Header status={status} connected={connected} onChanged={refresh} />

      {backendDown && (
        <div className="border-b border-red-800 bg-red-950/60 px-4 py-2 text-center text-sm text-red-200">
          ⚠ Cannot reach the backend at{" "}
          <code className="rounded bg-red-900/50 px-1">{API_BASE}</code> —{" "}
          {statusError}. Retrying…
        </div>
      )}

      <div className="mx-auto max-w-[1600px] px-4 py-4">
        {/* Control spans full width. */}
        <div className="mb-4">
          <ControlPanel status={status} onChanged={refresh} />
        </div>

        {/* Top row: account + equity curve. */}
        <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <AccountSummary status={status} />
          <EquityCurve refreshKey={version} />
        </div>

        {/* Selections + strategies. */}
        <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Selections status={status} />
          <StrategiesPanel refreshKey={version} onChanged={refresh} />
        </div>

        {/* News & sentiment. */}
        <div className="mb-4">
          <NewsPanel refreshKey={version} />
        </div>

        {/* Positions full width. */}
        <div className="mb-4">
          <Positions status={status} onChanged={refresh} />
        </div>

        {/* Approvals + manual trade. */}
        <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Approvals
            refreshKey={version}
            autonomyLevel={status?.autonomy_level ?? 0}
            onChanged={refresh}
          />
          <ManualTrade onChanged={refresh} />
        </div>

        {/* Orders + event log. */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Orders refreshKey={version} onChanged={refresh} />
          <EventLog events={events} />
        </div>

        <footer className="mt-6 flex flex-wrap items-center justify-between gap-2 border-t border-base-800 pt-3 text-xs text-slate-600">
          <span>
            API: <code className="text-slate-500">{API_BASE}</code>
          </span>
          <span>
            Last cycle:{" "}
            <span className="text-slate-500">
              {fmtDateTime(status?.last_cycle_at)}
            </span>
          </span>
        </footer>
      </div>
    </main>
  );
}
