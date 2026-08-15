"use client";

import { EngineEvent, fmtTime } from "@/lib/api";
import { Chip, Empty, Panel } from "./ui";

function eventColor(type: string): string {
  const t = type.toLowerCase();
  if (t.includes("error") || t.includes("halt") || t.includes("kill")) return "red";
  if (t.includes("fill") || t.includes("filled")) return "green";
  if (t.includes("order")) return "sky";
  if (t.includes("warn")) return "amber";
  if (t.includes("decision") || t.includes("selection")) return "violet";
  return "slate";
}

function compactJson(data: unknown): string {
  if (data === null || data === undefined) return "";
  if (typeof data === "string") return data;
  try {
    const s = JSON.stringify(data);
    return s.length > 200 ? `${s.slice(0, 200)}…` : s;
  } catch {
    return String(data);
  }
}

export function EventLog({ events }: { events: EngineEvent[] }) {
  return (
    <Panel
      title="Event Log"
      actions={<Chip color="slate">{events.length}</Chip>}
    >
      {events.length === 0 ? (
        <Empty>No events yet. Waiting for the engine…</Empty>
      ) : (
        <div className="max-h-96 space-y-1 overflow-auto font-mono text-xs">
          {events.map((e, i) => (
            <div
              key={`${e.timestamp}-${i}`}
              className="flex items-start gap-2 border-b border-base-800/70 py-1 last:border-0"
            >
              <span className="shrink-0 tabular-nums text-slate-500">
                {fmtTime(e.timestamp)}
              </span>
              <span className="shrink-0">
                <Chip color={eventColor(e.type)}>{e.type}</Chip>
              </span>
              <span className="break-all text-slate-400">{compactJson(e.data)}</span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
