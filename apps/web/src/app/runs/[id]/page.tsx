"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { RunTimeline, type TimelineEvent } from "@/components/RunTimeline";
import { ErrorState, Loading, StatusBadge } from "@/components/ui";
import { api, enc, must } from "@/lib/http";
import { useEventStream, useLoad } from "@/lib/hooks";

/** Agent run viewer: live node-by-node progress streamed from LangGraph (SSE), checkpoint history with replay,
 *  the graph rendered from code, and a link to the full trace. */
export default function RunView() {
  const { id } = useParams<{ id: string }>();
  const threadId = decodeURIComponent(id);
  const { data, error, loading, reload } = useLoad(() => must(api.GET("/api/runs/{thread_id}", { params: { path: { thread_id: threadId } } })), [threadId]);
  const [live, setLive] = useState<TimelineEvent[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const lastId = data?.events.length ? data.events[data.events.length - 1].id : 0;

  useEventStream(data ? `/api/runs/${enc(threadId)}/stream?after=${lastId}` : null, (type, d) => {
    if (type === "run_event") setLive((xs) => [...xs, { node: String(d.node), event: String(d.event), payload: d }]);
    if (type === "run_finished") { setLive([]); void reload(); }
  });

  if (error) return <ErrorState error={error} retry={reload} />;
  if (loading || !data) return <Loading lines={8} />;
  const stored: TimelineEvent[] = data.events.map((e) => ({ id: e.id, node: e.node, event: e.event, ts: e.ts, payload: e.payload }));
  const run = data.runs[data.runs.length - 1];
  const jobId = threadId.startsWith("bid:") ? threadId.split(":").slice(2).join(":") : null;

  async function replay(cp: string) {
    await api.POST("/api/runs/{thread_id}/replay", { params: { path: { thread_id: threadId } }, body: { checkpoint_id: cp } });
    setMsg("Replaying from that checkpoint - watch the timeline.");
  }

  return (
    <>
      <p className="small">{jobId ? <Link href={`/jobs/${enc(jobId)}`}>← Job</Link> : <Link href="/runs">← Runs</Link>}</p>
      <div className="spread">
        <h1>Agent run</h1>
        {run && <div className="row"><StatusBadge status={run.status} />
          <span className="small muted">{run.tokens} tokens · ${run.cost_usd.toFixed(4)} · {run.latency_s.toFixed(1)}s</span>
          {run.trace_url ? <a href={run.trace_url} target="_blank" rel="noreferrer">Full trace ↗</a> : <span className="small mono">trace {run.trace_id}</span>}</div>}
      </div>
      <p className="small mono muted">{threadId}</p>
      {msg && <div className="banner info" role="status">{msg}</div>}
      <div className="grid2">
        <section className="card" aria-label="Timeline">
          <h2 style={{ marginTop: 0 }}>Node-by-node {live.length > 0 && <span className="badge info">live</span>}</h2>
          <RunTimeline events={[...stored, ...live]} />
          {data.runs.length > 1 && <p className="small muted">{data.runs.length} runs on this thread (initial run, resumes after approval, replays).</p>}
        </section>
        <section className="card" aria-label="Checkpoints">
          <h2 style={{ marginTop: 0 }}>Checkpoint history</h2>
          <p className="small muted">Replay this job from any node (Postgres/SQLite checkpointer).</p>
          <table><thead><tr><th>Step</th><th>Wrote</th><th>Next</th><th /></tr></thead>
            <tbody>{data.checkpoints.slice(0, 25).map((c) => (
              <tr key={c.checkpoint_id}><td>{c.step}</td><td className="small">{c.node}</td><td className="small">{c.next.join(", ")}</td>
                <td>{c.next.length > 0 && c.next[0] !== "approval" && <button className="small" onClick={() => replay(c.checkpoint_id)}>Replay</button>}</td></tr>))}</tbody>
          </table>
        </section>
      </div>
      <details className="card" style={{ marginTop: 12 }}><summary>Graph (rendered from code)</summary><pre>{data.graph_mermaid}</pre></details>
    </>
  );
}
