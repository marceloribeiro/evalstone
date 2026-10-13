"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, wsUrl } from "@/lib/api";
import type { LiveEvent } from "@/lib/types";

/**
 * One socket per project page: POST /projects/{id}/ws-ticket (the bearer never travels on the
 * socket URL) → GET /ws/projects/{id}?ticket=… → every frame is dispatched to the handlers
 * registered for its `event` type. Reconnects with backoff; a `ping` every 25 s keeps proxies
 * from idling the connection.
 */
export type LiveHandler = (event: LiveEvent) => void;
type Status = "connecting" | "open" | "closed";

type Live = {
  status: Status;
  subscribe: (eventType: string | "*", handler: LiveHandler) => () => void;
  recent: LiveEvent[];
};

const Ctx = createContext<Live | null>(null);
const RECENT = 50;

export function WebSocketProvider({ projectId, children }: { projectId: string; children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("connecting");
  const [recent, setRecent] = useState<LiveEvent[]>([]);
  const handlers = useRef<Map<string, Set<LiveHandler>>>(new Map());

  const dispatch = useCallback((event: LiveEvent) => {
    if (event.event !== "hello" && event.event !== "pong") {
      setRecent((r) => [event, ...r].slice(0, RECENT));
    }
    for (const key of [event.event, "*"]) {
      handlers.current.get(key)?.forEach((h) => h(event));
    }
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let keepalive: ReturnType<typeof setInterval> | null = null;

    const connect = async () => {
      if (closed) return;
      setStatus("connecting");
      try {
        const { ticket } = await api<{ ticket: string }>(`/projects/${projectId}/ws-ticket`, { method: "POST" });
        const url = new URL(wsUrl(`/ws/projects/${projectId}`));
        url.searchParams.set("ticket", ticket);
        socket = new WebSocket(url.toString());
      } catch {
        schedule();
        return;
      }
      socket.onopen = () => {
        attempt = 0;
        setStatus("open");
        keepalive = setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send("ping"), 25_000);
      };
      socket.onmessage = (m) => {
        try {
          dispatch(JSON.parse(m.data) as LiveEvent);
        } catch {
          /* not JSON: ignore */
        }
      };
      socket.onclose = () => {
        if (keepalive) clearInterval(keepalive);
        setStatus("closed");
        schedule();
      };
      socket.onerror = () => socket?.close();
    };
    const schedule = () => {
      if (closed) return;
      attempt += 1;
      timer = setTimeout(connect, Math.min(30_000, 1_000 * 2 ** attempt));
    };
    connect();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      if (keepalive) clearInterval(keepalive);
      socket?.close();
    };
  }, [projectId, dispatch]);

  const subscribe = useCallback((eventType: string, handler: LiveHandler) => {
    const set = handlers.current.get(eventType) ?? new Set<LiveHandler>();
    set.add(handler);
    handlers.current.set(eventType, set);
    return () => {
      set.delete(handler);
    };
  }, []);

  const value = useMemo<Live>(() => ({ status, subscribe, recent }), [status, subscribe, recent]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLive(): Live {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useLive outside WebSocketProvider");
  return ctx;
}

/** Subscribe a handler to one event type for the component's lifetime. */
export function useLiveEvent(eventType: string | "*", handler: LiveHandler) {
  const { subscribe } = useLive();
  const ref = useRef(handler);
  useEffect(() => {
    ref.current = handler;
  });
  useEffect(() => subscribe(eventType, (e) => ref.current(e)), [eventType, subscribe]);
}
