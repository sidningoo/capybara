"use client";

import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Button, Empty, Panel } from "./ui";

export function DigestPanel({ refreshKey }: { refreshKey?: number }) {
  const { data, error, loading, refresh } = useApi<{ digest: string }>(
    (signal) => api.digest(signal),
    30000,
    refreshKey ?? 0
  );

  const digest = data?.digest?.trim() ?? "";

  return (
    <Panel
      title="Daily Digest"
      actions={
        <Button variant="ghost" onClick={refresh} title="Refresh digest">
          Refresh
        </Button>
      }
    >
      {loading && !data ? (
        <Empty>Loading…</Empty>
      ) : error && !data ? (
        <Empty>Could not load digest.</Empty>
      ) : digest.length === 0 ? (
        <Empty>No digest available.</Empty>
      ) : (
        <pre className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-200">
          {digest}
        </pre>
      )}
    </Panel>
  );
}
