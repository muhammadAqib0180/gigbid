"use client";

export type TimelineEvent = { id?: number | string; node: string; event: string; ts?: string; payload?: Record<string, unknown>; summary?: unknown; latency_s?: unknown };

/** Node-by-node progress of a LangGraph run (live via SSE, or replayed from stored events). */
export function RunTimeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) return <p className="muted small">No events yet.</p>;
  return (
    <ol className="timeline" aria-live="polite" data-testid="run-timeline">
      {events.map((e, i) => {
        const p = { ...(e.payload || {}), ...e } as Record<string, unknown>;
        const detail = (p.summary as string) || (p.reason as string) || (p.error as string) || "";
        return (
          <li key={e.id ?? i}>
            <span className={`dot ${e.event}`} aria-hidden />
            <span><strong>{e.node}</strong> <span className="muted">{e.event}</span></span>
            <span className="small">{detail}{p.latency_s != null && <span className="muted"> · {Number(p.latency_s).toFixed(2)}s</span>}</span>
          </li>
        );
      })}
    </ol>
  );
}
