"use client";
import { Empty, ErrorState, Loading } from "@/components/ui";
import { api, must, pct } from "@/lib/http";
import { useLoad } from "@/lib/hooks";

/* eslint-disable @typescript-eslint/no-explicit-any */
function Bars({ rows, value, label }: { rows: any[]; value: string; label: string }) {
  if (!rows.length) return <p className="small muted">No data yet.</p>;
  return (
    <table aria-label={label}>
      <tbody>{rows.map((r) => (
        <tr key={r.key}>
          <td className="small" style={{ width: "35%" }}>{r.key}</td>
          <td><div className="bar" style={{ height: 12 }}><span style={{ width: `${Math.round((r[value] || 0) * 100)}%` }} /></div></td>
          <td className="small" style={{ width: 110 }}>{pct(r[value])} <span className="muted">(n={r.sent})</span></td>
        </tr>))}</tbody>
    </table>
  );
}

export default function Analytics() {
  const { data, error, loading, reload } = useLoad(() => must(api.GET("/api/analytics")), []);
  if (error) return <ErrorState error={error} retry={reload} />;
  if (loading || !data) return <Loading lines={6} />;
  const c: any = data.connects;
  const cl: any = data.cost_latency;
  return (
    <>
      <h1>Analytics</h1>
      <div className="grid3">
        <div className="card"><div className="small muted">Proposals sent</div><div className="stat">{c.proposals_sent}</div></div>
        <div className="card"><div className="small muted">Replies</div><div className="stat">{c.replies}</div></div>
        <div className="card"><div className="small muted">Connects spent / per reply</div><div className="stat">{c.spent} <span className="small muted">/ {c.connects_per_reply ?? "-"}</span></div></div>
      </div>
      <div className="grid2" style={{ marginTop: 12 }}>
        <section className="card"><h2 style={{ marginTop: 0 }}>Reply rate by category</h2><Bars rows={data.by_category} value="reply_rate" label="reply rate by category" />
          <h2>Hire rate by category</h2><Bars rows={data.by_category} value="hire_rate" label="hire rate by category" /></section>
        <section className="card"><h2 style={{ marginTop: 0 }}>Reply rate by proposal strategy (A/B)</h2><Bars rows={data.by_strategy} value="reply_rate" label="reply rate by strategy" />
          <h2>Funnel</h2>
          <table><tbody>{Object.entries(data.funnel).map(([k, v]) => <tr key={k}><td className="small">{k}</td><td>{v}</td></tr>)}</tbody></table></section>
      </div>
      <div className="grid2" style={{ marginTop: 12 }}>
        <section className="card"><h2 style={{ marginTop: 0 }}>Cost and latency</h2>
          <table><tbody>
            <tr><td className="small">Jobs analysed</td><td>{cl.runs}</td></tr>
            <tr><td className="small">p50 / p95 latency per job</td><td>{cl.p50_latency_s_per_job}s / {cl.p95_latency_s_per_job}s</td></tr>
            <tr><td className="small">USD per job (p50)</td><td>${cl.usd_per_job_p50}</td></tr>
            <tr><td className="small">p95 latency per proposal</td><td>{cl.p95_latency_s_per_proposal}s</td></tr>
            <tr><td className="small">USD per proposal (mean)</td><td>${cl.usd_per_proposal_mean}</td></tr>
            <tr><td className="small">Tokens (all runs)</td><td>{cl.tokens_total}</td></tr>
          </tbody></table></section>
        <section className="card"><h2 style={{ marginTop: 0 }}>Top rejection reasons</h2>
          {data.rejection_reasons.length === 0 ? <Empty title="No rejections yet" /> :
            <ol className="small">{data.rejection_reasons.map((r: any) => <li key={r.reason}>{r.reason} ({r.count})</li>)}</ol>}
          <h2>Decisions</h2>
          <p className="small">{Object.entries(data.decisions).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p></section>
      </div>
    </>
  );
}
