"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ActionBadge, ErrorState, FitBar, Loading, RiskBadge, StatusBadge } from "@/components/ui";
import { api, enc, fmtMoney, must } from "@/lib/http";
import { useEventStream, useLoad } from "@/lib/hooks";

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const jobId = decodeURIComponent(id);
  const { data: j, error, loading, reload } = useLoad(() => must(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: jobId } } })), [jobId]);
  useEventStream("/api/events/stream", (type, d) => {
    if (type === "run_finished" && d.job_id === jobId) void reload();
  });

  if (error) return <ErrorState error={error} retry={reload} />;
  if (loading || !j) return <Loading lines={8} />;
  const spec: any = j.job_spec || {};
  const risk: any = j.risk || {};
  const fit: any = j.fit || {};
  const dec: any = j.decision || {};
  const price: any = j.price_quote || {};

  async function analyze(force = false) {
    await api.POST("/api/jobs/{job_id}/analyze", { params: { path: { job_id: jobId }, query: { force } } });
    void reload();
  }

  return (
    <>
      <p className="small"><Link href="/inbox">← Inbox</Link></p>
      <div className="spread">
        <h1>{j.title}</h1>
        <div className="row">
          <StatusBadge status={j.status} />
          {j.status === "awaiting_approval" && <Link className="btn" href={`/studio/${enc(jobId)}`}>Open proposal studio</Link>}
          <Link className="btn" href={`/runs/${enc(j.thread_id)}`}>Agent run</Link>
          {["queued", "error", "dead_letter", "needs_attention", "skipped", "watching"].includes(j.status) &&
            <button onClick={() => analyze(j.status !== "queued")}>Re-analyse</button>}
        </div>
      </div>
      {j.status_reason && <p className="muted">{j.status_reason}</p>}
      {(j.errors ?? []).length > 0 && <div className="banner bad">{(j.errors ?? []).join("; ")}</div>}

      <div className="grid3">
        <div className="card"><div className="small muted">Fit</div><FitBar value={j.fit_score} /><div className="small muted">{fit.retrieval_variant}</div></div>
        <div className="card"><div className="small muted">Risk</div><RiskBadge score={j.risk_score} scam={j.is_scam} flags={j.risk_flags} /></div>
        <div className="card"><div className="small muted">Decision</div><ActionBadge action={j.action} /> <span className="small">{(dec.reasons || []).join("; ")}</span></div>
      </div>

      <div className="grid2" style={{ marginTop: 12 }}>
        <section className="card" aria-label="Job spec">
          <h2 style={{ marginTop: 0 }}>JobSpec</h2>
          <p className="small">{spec.summary || (j.job as any)?.description?.slice(0, 300)}</p>
          <p className="small"><strong>Skills:</strong> {(spec.required_skills || []).join(", ") || "-"}</p>
          <p className="small"><strong>Deliverables:</strong> {(spec.deliverables || []).join("; ") || "-"}</p>
          <p className="small"><strong>Budget:</strong> {spec.is_hourly ? `${fmtMoney(spec.budget_min)}-${fmtMoney(spec.budget_max)}/h` : fmtMoney(spec.budget_max)} · {spec.experience_level || ""}</p>
          <p className="small"><strong>Screening questions:</strong> {(spec.screening_questions || []).join(" · ") || "none"}</p>
          <p className="small"><strong>Hidden needs:</strong> {(spec.hidden_needs || []).join("; ") || "-"}</p>
          <details><summary className="small">Original post (untrusted text)</summary><pre>{(j.job as any)?.description}</pre>
            <p className="small muted">Source: {(j.job as any)?.source}</p></details>
        </section>
        <section className="card" aria-label="Risk report">
          <h2 style={{ marginTop: 0 }}>Risk report</h2>
          <p className="small">{risk.explanation}</p>
          <p className="small"><strong>Flags:</strong> {(risk.flags || []).join(", ") || "none"}</p>
          <p className="small"><strong>Client quality:</strong> {risk.client_quality != null ? `${Math.round(risk.client_quality * 100)}%` : "-"}</p>
          {risk.injection_detected && <div className="banner warn small"><strong>Prompt injection detected and ignored:</strong> “{(risk.injection_spans || [])[0]}”</div>}
          <h2>Price</h2>
          <p><strong>{fmtMoney(price.amount, price.unit)}</strong> <span className="small muted">(range {fmtMoney(price.low)}-{fmtMoney(price.high)}) · {price.connects_cost} Connects · worth it: {String(price.connects_worth_it ?? "-")}</span></p>
          <ul className="small">{(price.rationale || []).map((r: string) => <li key={r}>{r}</li>)}</ul>
        </section>
      </div>

      <section className="card" style={{ marginTop: 12 }} aria-label="Requirement to evidence matrix">
        <h2 style={{ marginTop: 0 }}>Requirement → evidence</h2>
        {(j.evidence_matrix ?? []).length === 0 ? <p className="muted small">Not analysed yet.</p> : (
          <table>
            <thead><tr><th>Requirement</th><th>Proven?</th><th>Portfolio items</th><th>Score</th></tr></thead>
            <tbody>{(j.evidence_matrix ?? []).map((m: any) => (
              <tr key={m.requirement_id}>
                <td className="small">{m.requirement}</td>
                <td>{m.covered ? <span className="badge ok">yes</span> : <span className="badge bad">no evidence</span>}</td>
                <td className="small mono">{(m.item_ids || []).join(", ")}</td>
                <td className="small">{m.best_score?.toFixed?.(2)}</td>
              </tr>))}</tbody>
          </table>
        )}
        <p className="small muted">{(fit.reasons || []).join(" · ")}</p>
      </section>
      {j.submission && <div className="card"><h2 style={{ marginTop: 0 }}>Submission</h2><pre>{JSON.stringify(j.submission, null, 2)}</pre></div>}
    </>
  );
}
