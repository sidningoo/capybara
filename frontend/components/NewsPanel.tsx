"use client";

import { api, News } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Chip, Empty, Panel, SentimentBar } from "./ui";

const MAX_HEADLINES = 3;

export function NewsPanel({ refreshKey }: { refreshKey?: number }) {
  const { data, error, loading } = useApi<News>(
    (signal) => api.news(signal),
    30000,
    refreshKey ?? 0
  );

  const sentiment = data?.sentiment ?? {};
  // Only surface symbols that actually have recent news, sorted by symbol.
  const rows = Object.entries(sentiment)
    .filter(([, s]) => s.n_articles > 0)
    .sort(([a], [b]) => a.localeCompare(b));

  return (
    <Panel title="News & Sentiment">
      {loading && !data ? (
        <Empty>Loading…</Empty>
      ) : error && !data ? (
        <Empty>Could not load news.</Empty>
      ) : rows.length === 0 ? (
        <Empty>No recent news.</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map(([symbol, s]) => {
            const headlines = s.headlines.slice(0, MAX_HEADLINES);
            return (
              <li
                key={symbol}
                className="rounded-lg border border-base-700 bg-base-900/40 px-3 py-2.5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-100">{symbol}</span>
                    <Chip color="slate">
                      {s.n_articles} {s.n_articles === 1 ? "article" : "articles"}
                    </Chip>
                  </div>
                  <SentimentBar score={s.score} />
                </div>
                {headlines.length > 0 && (
                  <ul className="mt-1.5 flex flex-col gap-1">
                    {headlines.map((headline, i) => (
                      <li
                        key={i}
                        className="truncate text-xs text-slate-400"
                        title={headline}
                      >
                        • {headline}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
