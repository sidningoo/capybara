"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, api, EngineEvent, Status } from "./api";

function wsUrl(): string {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}/ws`;
}

const MAX_EVENTS = 500;

export interface LiveStatus {
  status: Status | null;
  statusError: string | null;
  connected: boolean;
  events: EngineEvent[];
  /** Bump this to have consumers know a POST-worthy refresh happened. */
  version: number;
  /** Force an immediate status refresh + notify consumers. */
  refresh: () => void;
}

/**
 * Manages the live connection to the backend:
 *  - Opens a WebSocket to `${API_BASE}/ws`.
 *  - The first frame is a `{type:"snapshot", data}` — used to seed status.
 *  - Subsequent `{timestamp,type,data}` frames are appended to the event log
 *    and trigger a status refresh.
 *  - If the WS drops, it reconnects with exponential backoff.
 *  - Regardless of WS health, it polls `/api/status` every 5s as a fallback.
 */
export function useLiveStatus(pollMs = 5000): LiveStatus {
  const [status, setStatus] = useState<Status | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<EngineEvent[]>([]);
  const [version, setVersion] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);

  const pushEvents = useCallback((incoming: EngineEvent[]) => {
    setEvents((prev) => {
      const merged = [...incoming, ...prev];
      return merged.slice(0, MAX_EVENTS);
    });
  }, []);

  const pollStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      const s = await api.status(signal);
      if (!mountedRef.current) return;
      setStatus(s);
      setStatusError(null);
    } catch (err) {
      if (!mountedRef.current) return;
      if ((err as Error)?.name === "AbortError") return;
      setStatusError((err as Error)?.message || "Backend unreachable");
    }
  }, []);

  const refresh = useCallback(() => {
    setVersion((v) => v + 1);
    pollStatus();
  }, [pollStatus]);

  // WebSocket lifecycle.
  useEffect(() => {
    mountedRef.current = true;

    const connect = () => {
      if (!mountedRef.current) return;
      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl());
      } catch {
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnected(true);
        backoffRef.current = 1000;
      };

      ws.onmessage = (ev) => {
        if (!mountedRef.current) return;
        try {
          const msg = JSON.parse(ev.data);
          if (msg && msg.type === "snapshot" && msg.data) {
            setStatus(msg.data as Status);
            setStatusError(null);
          } else if (msg && typeof msg.type === "string") {
            pushEvents([msg as EngineEvent]);
            // Any live event may change engine state — refresh status.
            pollStatus();
          }
        } catch {
          /* ignore malformed frames */
        }
      };

      ws.onerror = () => {
        // onclose will handle reconnect.
        try {
          ws.close();
        } catch {
          /* noop */
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setConnected(false);
        scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      const delay = backoffRef.current;
      backoffRef.current = Math.min(backoffRef.current * 2, 15000);
      reconnectRef.current = setTimeout(connect, delay);
    };

    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        try {
          wsRef.current.close();
        } catch {
          /* noop */
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fallback polling — always runs regardless of WS health.
  useEffect(() => {
    const controller = new AbortController();
    pollStatus(controller.signal);
    const id = setInterval(() => pollStatus(), pollMs);
    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, [pollMs, pollStatus]);

  // Seed the event log from history once on mount.
  useEffect(() => {
    let active = true;
    api
      .events(200)
      .then((res) => {
        if (!active) return;
        // Show newest first.
        const hist = [...res.events].reverse();
        setEvents((prev) => {
          const seen = new Set(prev.map((e) => `${e.timestamp}:${e.type}`));
          const fresh = hist.filter(
            (e) => !seen.has(`${e.timestamp}:${e.type}`)
          );
          return [...prev, ...fresh].slice(0, MAX_EVENTS);
        });
      })
      .catch(() => {
        /* backend down — banner handles it */
      });
    return () => {
      active = false;
    };
  }, []);

  return { status, statusError, connected, events, version, refresh };
}
