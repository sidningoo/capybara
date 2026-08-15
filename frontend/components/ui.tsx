"use client";

import { ReactNode } from "react";

// ───────────────────────── Panel ─────────────────────────

export function Panel({
  title,
  actions,
  children,
  className = "",
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-base-700 bg-base-850 shadow-lg shadow-black/20 ${className}`}
    >
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-base-700 px-4 py-2.5">
          {title && (
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {title}
            </h2>
          )}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

// ───────────────────────── Button ─────────────────────────

type ButtonVariant = "default" | "primary" | "danger" | "ghost" | "success";

const buttonStyles: Record<ButtonVariant, string> = {
  default:
    "bg-base-700 hover:bg-base-600 text-slate-100 border border-base-600",
  primary: "bg-sky-600 hover:bg-sky-500 text-white border border-sky-500",
  danger: "bg-red-600 hover:bg-red-500 text-white border border-red-500",
  success:
    "bg-emerald-600 hover:bg-emerald-500 text-white border border-emerald-500",
  ghost:
    "bg-transparent hover:bg-base-700 text-slate-300 border border-transparent",
};

export function Button({
  children,
  onClick,
  variant = "default",
  disabled = false,
  type = "button",
  className = "",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
  title?: string;
}) {
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${buttonStyles[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

// ───────────────────────── Chips / badges ─────────────────────────

export function Chip({
  children,
  color = "slate",
  className = "",
}: {
  children: ReactNode;
  color?: string;
  className?: string;
}) {
  const map: Record<string, string> = {
    slate: "bg-slate-700/50 text-slate-300 border-slate-600",
    green: "bg-emerald-900/40 text-emerald-300 border-emerald-700",
    red: "bg-red-900/40 text-red-300 border-red-700",
    amber: "bg-amber-900/40 text-amber-300 border-amber-700",
    sky: "bg-sky-900/40 text-sky-300 border-sky-700",
    violet: "bg-violet-900/40 text-violet-300 border-violet-700",
    gray: "bg-gray-700/40 text-gray-300 border-gray-600",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${
        map[color] || map.slate
      } ${className}`}
    >
      {children}
    </span>
  );
}

// Stable-ish color per regime string.
export function regimeColor(regime: string): string {
  const r = (regime || "").toLowerCase();
  if (r.includes("bull") || r.includes("trend_up")) return "green";
  if (r.includes("bear") || r.includes("trend_down")) return "red";
  if (r.includes("volatile") || r.includes("high_vol")) return "amber";
  if (r.includes("range") || r.includes("mean")) return "sky";
  if (r.includes("breakout")) return "violet";
  return "slate";
}

// ───────────────────────── Confidence bar ─────────────────────────

export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const color =
    pct >= 66 ? "bg-emerald-500" : pct >= 33 ? "bg-amber-500" : "bg-slate-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-base-700">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="tabular-nums text-xs text-slate-400">
        {pct.toFixed(0)}%
      </span>
    </div>
  );
}

// ───────────────────────── Sentiment ─────────────────────────

// Classify a sentiment score in [-1, 1] into a semantic bucket.
export function sentimentBucket(score: number): "positive" | "negative" | "neutral" {
  if (score > 0.15) return "positive";
  if (score < -0.15) return "negative";
  return "neutral";
}

// A compact bidirectional bar for a sentiment score in [-1, 1]. The bar fills
// from the center: green to the right for positive, red to the left for
// negative, slate for neutral.
export function SentimentBar({ score }: { score: number }) {
  const clamped = Math.max(-1, Math.min(1, score));
  const bucket = sentimentBucket(clamped);
  const magnitude = Math.abs(clamped) * 50; // half-width percentage
  const fillColor =
    bucket === "positive"
      ? "bg-emerald-500"
      : bucket === "negative"
        ? "bg-red-500"
        : "bg-slate-500";
  const textColor =
    bucket === "positive"
      ? "text-emerald-300"
      : bucket === "negative"
        ? "text-red-300"
        : "text-slate-400";
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-1.5 w-16 overflow-hidden rounded-full bg-base-700">
        {/* center divider */}
        <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-base-600" />
        <div
          className={`absolute top-0 h-full ${fillColor}`}
          style={
            clamped >= 0
              ? { left: "50%", width: `${magnitude}%` }
              : { right: "50%", width: `${magnitude}%` }
          }
        />
      </div>
      <span className={`tabular-nums text-xs ${textColor}`}>
        {clamped >= 0 ? "+" : ""}
        {clamped.toFixed(2)}
      </span>
    </div>
  );
}

// A small chip for a trading horizon: "intraday" vs "swing".
export function HorizonChip({ horizon }: { horizon: string }) {
  const h = (horizon || "").toLowerCase();
  const color = h === "intraday" ? "sky" : "slate";
  return <Chip color={color}>{horizon || "—"}</Chip>;
}

// ───────────────────────── Empty state ─────────────────────────

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="py-6 text-center text-sm text-slate-500">{children}</div>
  );
}
