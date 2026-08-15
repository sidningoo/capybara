"use client";

import { api, control, Strategies } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAction } from "@/lib/useAction";
import { Button, Chip, Empty, Panel, regimeColor } from "./ui";

export function StrategiesPanel({
  refreshKey,
  onChanged,
}: {
  refreshKey: number;
  onChanged: () => void;
}) {
  const { data, error, loading, refresh } = useApi<Strategies>(
    (signal) => api.strategies(signal),
    5000,
    refreshKey
  );
  const { run, pending } = useAction(() => {
    refresh();
    onChanged();
  });

  const pinned = data?.pinned ?? null;
  const blocked = new Set(data?.blocked ?? []);
  const playbook = data?.playbook ?? [];

  return (
    <Panel
      title="Strategies / Playbook"
      actions={
        <div className="flex items-center gap-2">
          {pinned && (
            <Chip color="sky">
              pinned: {pinned}
            </Chip>
          )}
          <Button
            variant="ghost"
            onClick={() => run(() => control.pin("cash"), "Pinned to cash")}
            disabled={pending}
            title="Force the engine to hold cash"
          >
            Pin Cash
          </Button>
          <Button
            variant="ghost"
            onClick={() => run(() => control.pin(null), "Unpinned")}
            disabled={pending || !pinned}
          >
            Unpin
          </Button>
        </div>
      }
    >
      {loading && !data ? (
        <Empty>Loading…</Empty>
      ) : error && !data ? (
        <Empty>Could not load strategies.</Empty>
      ) : playbook.length === 0 ? (
        <Empty>No strategies in playbook.</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {playbook.map((s) => {
            const isPinned = pinned === s.name;
            const isBlocked = blocked.has(s.name);
            return (
              <li
                key={s.name}
                className={`rounded-lg border px-3 py-2.5 ${
                  isBlocked
                    ? "border-red-900/60 bg-red-950/20"
                    : isPinned
                      ? "border-sky-800 bg-sky-950/20"
                      : "border-base-700 bg-base-900/40"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-100">{s.name}</span>
                    {isPinned && <Chip color="sky">pinned</Chip>}
                    {isBlocked && <Chip color="red">blocked</Chip>}
                    <span className="text-xs text-slate-500">
                      max {(s.max_weight * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant={isPinned ? "primary" : "ghost"}
                      onClick={() =>
                        run(
                          () => control.pin(isPinned ? null : s.name),
                          isPinned ? "Unpinned" : `Pinned ${s.name}`
                        )
                      }
                      disabled={pending || isBlocked}
                      title={isBlocked ? "Unblock before pinning" : "Pin this strategy"}
                    >
                      {isPinned ? "Unpin" : "Pin"}
                    </Button>
                    <Button
                      variant={isBlocked ? "danger" : "ghost"}
                      onClick={() =>
                        run(
                          () => control.block(s.name, !isBlocked),
                          isBlocked ? `Unblocked ${s.name}` : `Blocked ${s.name}`
                        )
                      }
                      disabled={pending}
                    >
                      {isBlocked ? "Unblock" : "Block"}
                    </Button>
                  </div>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {s.suited_regimes.map((r) => (
                    <Chip key={r} color={regimeColor(r)}>
                      {r}
                    </Chip>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
