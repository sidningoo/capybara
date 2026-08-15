"use client";

import { useState } from "react";
import { api, control, Preferences, EffectiveRisk } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAction } from "@/lib/useAction";
import { Button, Empty, Panel } from "./ui";

// Human-readable, one-line summary of what a risk profile maps to.
function riskSummary(r: EffectiveRisk): string {
  const parts = [
    `Max position ${r.max_position_pct}%`,
    `Max positions ${r.max_concurrent_positions}`,
    `Daily-loss stop ${r.max_daily_loss_pct}%`,
    `Target vol ${r.target_vol}%`,
    `Max sector ${r.max_sector_pct}%`,
  ];
  return parts.join(" · ");
}

function profileLabel(p: string): string {
  return p.charAt(0).toUpperCase() + p.slice(1);
}

export function PreferencesPanel({
  refreshKey,
  onChanged,
}: {
  refreshKey: number;
  onChanged: () => void;
}) {
  const { data, error, loading, refresh } = useApi<Preferences>(
    (signal) => api.preferences(signal),
    10000,
    refreshKey
  );
  const { run, pending } = useAction(() => {
    refresh();
    onChanged();
  });
  const [newSymbol, setNewSymbol] = useState("");

  const profiles = data?.available_profiles ?? [];
  const active = data?.risk_profile ?? null;
  const watchlist = data?.watchlist ?? [];

  const selectProfile = (profile: string) => {
    if (profile === active) return;
    run(() => control.setRisk(profile), `Risk profile set to ${profileLabel(profile)}`);
  };

  const removeSymbol = (symbol: string) => {
    const remaining = watchlist.filter((s) => s !== symbol);
    run(() => control.setWatchlist(remaining), `Removed ${symbol} from watchlist`);
  };

  const addSymbol = () => {
    const sym = newSymbol.trim().toUpperCase();
    if (!sym) return;
    if (watchlist.includes(sym)) {
      setNewSymbol("");
      return;
    }
    run(() => control.setWatchlist([...watchlist, sym]), `Added ${sym} to watchlist`).then(
      (ok) => {
        if (ok) setNewSymbol("");
      }
    );
  };

  const inputCls =
    "rounded-md border border-base-600 bg-base-900 px-2.5 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none";

  return (
    <Panel title="Preferences">
      <p className="mb-3 text-xs text-slate-500">
        Nudge the bot: pick a risk appetite and choose what it may trade. Changes
        apply on the next cycle.
      </p>

      {loading && !data ? (
        <Empty>Loading…</Empty>
      ) : error && !data ? (
        <Empty>Could not load preferences.</Empty>
      ) : !data ? (
        <Empty>No preferences available.</Empty>
      ) : (
        <div className="flex flex-col gap-5">
          {/* Risk profile selector */}
          <div>
            <div className="mb-2 text-[11px] uppercase tracking-wider text-slate-500">
              Risk profile
            </div>
            <div className="inline-flex flex-wrap gap-1 rounded-lg border border-base-700 bg-base-900/40 p-1">
              {profiles.map((p) => {
                const isActive = p === active;
                return (
                  <Button
                    key={p}
                    variant={isActive ? "primary" : "ghost"}
                    onClick={() => selectProfile(p)}
                    disabled={pending}
                    title={`Use the ${profileLabel(p)} risk profile`}
                  >
                    {profileLabel(p)}
                  </Button>
                );
              })}
            </div>
            <p className="mt-2 text-xs text-slate-400">
              {riskSummary(data.effective_risk)}
            </p>
          </div>

          {/* Watchlist editor */}
          <div>
            <div className="mb-2 text-[11px] uppercase tracking-wider text-slate-500">
              Watchlist
            </div>
            {watchlist.length === 0 ? (
              <p className="mb-2 text-xs text-slate-500">
                No symbols yet — add one below.
              </p>
            ) : (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {watchlist.map((sym) => (
                  <span
                    key={sym}
                    className="inline-flex items-center gap-1.5 rounded-full border border-slate-600 bg-slate-700/50 px-2 py-0.5 text-xs font-medium text-slate-300"
                  >
                    {sym}
                    <button
                      type="button"
                      onClick={() => removeSymbol(sym)}
                      disabled={pending}
                      title={`Remove ${sym}`}
                      className="text-slate-400 transition-colors hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                addSymbol();
              }}
            >
              <input
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value)}
                placeholder="AAPL"
                className={`${inputCls} w-28 uppercase`}
              />
              <Button
                type="submit"
                variant="default"
                disabled={pending || !newSymbol.trim()}
              >
                Add
              </Button>
            </form>
          </div>
        </div>
      )}
    </Panel>
  );
}
