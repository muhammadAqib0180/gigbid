"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./http";

/** Load data with explicit loading / error / data states and a reload function. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(e as Error);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, loading, reload, setData };
}

/** Subscribe to a Server-Sent Events URL; falls back to nothing if EventSource is unavailable. */
export function useEventStream(url: string | null, onEvent: (type: string, data: Record<string, unknown>) => void) {
  const cb = useRef(onEvent);
  cb.current = onEvent;
  useEffect(() => {
    if (!url || typeof EventSource === "undefined") return;
    const es = new EventSource(url, { withCredentials: true });
    const types = ["run_event", "run_started", "run_finished", "degraded", "health", "pipeline_updated", "scout_finished", "message"];
    const handlers = types.map((t) => {
      const h = (ev: MessageEvent) => {
        try {
          cb.current(t, JSON.parse(ev.data));
        } catch {
          /* ignore malformed */
        }
      };
      es.addEventListener(t, h as EventListener);
      return [t, h] as const;
    });
    return () => {
      handlers.forEach(([t, h]) => es.removeEventListener(t, h as EventListener));
      es.close();
    };
  }, [url]);
}
