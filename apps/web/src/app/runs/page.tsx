"use client";
import Link from "next/link";
import { Empty, ErrorState, Loading, StatusBadge } from "@/components/ui";
import { api, enc, must } from "@/lib/http";
import { useEventStream, useLoad } from "@/lib/hooks";

export default function Runs() {
  const { data, error, loading, reload } = useLoad(() => must(api.GET("/api/runs", { params: { query: { limit: 80 } } })), []);
  useEventStream("/api/events/stream", (type) => {
    if (type === "run_started" || type === "run_finished") void reload();
  });
  if (error) return <ErrorState error={error} retry={reload} />;
  if (loading || !data) return <Loading />;
  return (
    <>
      <h1>Agent runs</h1>
      {data.length === 0 ? <Empty title="No runs yet" /> : (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table>
            <thead><tr><th>Thread</th><th>Kind</th><th>Status</th><th className="hide-sm">Tokens</th><th className="hide-sm">Cost</th><th>Latency</th><th className="hide-sm">Trace</th></tr></thead>
            <tbody>{data.map((r) => (
              <tr key={r.id}>
                <td className="small"><Link href={`/runs/${enc(r.thread_id)}`}>{r.thread_id.split(":").slice(2).join(":")}</Link></td>
                <td>{r.kind}</td><td><StatusBadge status={r.status} /></td>
                <td className="hide-sm">{r.tokens}</td><td className="hide-sm">${r.cost_usd.toFixed(4)}</td><td>{r.latency_s.toFixed(1)}s</td>
                <td className="hide-sm small mono">{r.trace_url ? <a href={r.trace_url} target="_blank" rel="noreferrer">trace</a> : r.trace_id.slice(0, 8)}</td>
              </tr>))}</tbody>
          </table>
        </div>)}
    </>
  );
}
