"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface UseApiResult<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}

/**
 * Small polling fetch hook. Calls `fetcher` immediately and then every
 * `intervalMs`. Returns data/error/loading plus a manual `refresh`.
 * `refreshKey` can be bumped by the caller (e.g. after a POST) to force
 * an immediate re-fetch.
 */
export function useApi<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  intervalMs = 5000,
  refreshKey = 0
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  // Keep the latest fetcher without retriggering the effect on every render.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    const run = async () => {
      try {
        const result = await fetcherRef.current(controller.signal);
        if (!active) return;
        setData(result);
        setError(null);
      } catch (err) {
        if (!active) return;
        if ((err as Error)?.name === "AbortError") return;
        setError((err as Error)?.message || "Request failed");
      } finally {
        if (active) setLoading(false);
      }
    };

    run();
    const id = setInterval(run, intervalMs);
    return () => {
      active = false;
      controller.abort();
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, refreshKey, tick]);

  return { data, error, loading, refresh };
}
