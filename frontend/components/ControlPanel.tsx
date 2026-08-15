"use client";

import { useState } from "react";
import { control, Status } from "@/lib/api";
import { useAction } from "@/lib/useAction";
import { Button, Panel } from "./ui";

function KillDialog({
  onConfirm,
  onCancel,
  pending,
}: {
  onConfirm: () => void;
  onCancel: () => void;
  pending: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-md rounded-xl border border-red-700 bg-base-850 p-6 shadow-2xl">
        <h3 className="text-lg font-bold text-red-300">⚠ Activate Kill Switch?</h3>
        <p className="mt-2 text-sm text-slate-300">
          This halts the engine immediately and <b>flattens all positions</b>{" "}
          (sends market orders to close everything). This cannot be undone.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={pending}>
            {pending ? "Killing…" : "Kill & Flatten"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ControlPanel({
  status,
  onChanged,
}: {
  status: Status | null;
  onChanged: () => void;
}) {
  const { run, pending } = useAction(onChanged);
  const [showKill, setShowKill] = useState(false);

  const state = status?.state;
  const halted = state === "halted";
  const killed = status?.guardrails?.kill_switch;

  const doKill = async () => {
    const ok = await run(() => control.kill(true), "Kill switch activated — flattening positions");
    if (ok) setShowKill(false);
  };

  return (
    <Panel title="Engine Control">
      {halted && status?.halt_reason && (
        <div className="mb-3 rounded-lg border border-red-700 bg-red-950/50 px-3 py-2 text-sm text-red-200">
          <span className="font-semibold">HALTED:</span> {status.halt_reason}
        </div>
      )}
      {killed && (
        <div className="mb-3 rounded-lg border border-red-800 bg-red-950/40 px-3 py-2 text-xs text-red-300">
          Kill switch is engaged. Clear the halt to resume trading.
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          variant="success"
          onClick={() => run(() => control.start(), "Engine started")}
          disabled={pending}
        >
          ▶ Start
        </Button>
        <Button
          onClick={() => run(() => control.pause(), "Engine paused")}
          disabled={pending}
        >
          ⏸ Pause
        </Button>
        <Button
          onClick={() => run(() => control.resume(), "Engine resumed")}
          disabled={pending}
        >
          ⏵ Resume
        </Button>
        <Button
          onClick={() => run(() => control.stop(), "Engine stopped")}
          disabled={pending}
        >
          ⏹ Stop
        </Button>
        <Button
          onClick={() => run(() => control.clearHalt(), "Halt cleared")}
          disabled={pending}
          variant={halted ? "primary" : "default"}
        >
          ⟲ Clear Halt
        </Button>

        <div className="ml-auto">
          <Button variant="danger" onClick={() => setShowKill(true)} disabled={pending}>
            ⛔ KILL SWITCH
          </Button>
        </div>
      </div>

      {showKill && (
        <KillDialog
          onConfirm={doKill}
          onCancel={() => setShowKill(false)}
          pending={pending}
        />
      )}
    </Panel>
  );
}
