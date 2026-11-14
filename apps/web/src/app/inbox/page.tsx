"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ActionBadge, Empty, ErrorState, FitBar, Loading, RiskBadge, StatusBadge } from "@/components/ui";
import { api, fmtMoney, must, type Schemas } from "@/lib/http";
import { useEventStream, useLoad } from "@/lib/hooks";

type Job = Schemas["JobSummary"];

export default function Inbox() {
  const router = useRouter();
  const { data, error, loading, reload } = useLoad(() => must(api.GET("/api/jobs")), []);
  const [filter, setFilter] = useState<"all" | "approve" | "bid" | "skip" | "risky">("all");
  const [q, setQ] = useState("");
  const [scouting, setScouting] = useState(false);

  useEventStream("/api/events/stream", (type) => {
    if (type === "run_finished" || type === "scout_finished") void reload();
  });

  const jobs = useMemo(() => (data || []).filter((j: Job) => {
    if (q && !j.title.toLowerCase().includes(q.toLowerCase())) return false;
    if (filter === "approve") return j.status === "awaiting_approval";
    if (filter === "bid") return j.action === "bid";
    if (filter === "skip") return j.action === "skip" || j.status === "duplicate";
    if (filter === "risky") return j.is_scam || (j.risk_score ?? 0) >= 0.3;
    return true;
  }), [data, filter, q]);

  async function scout() {
    setScouting(true);
    await api.POST("/api/scout");
    setScouting(false);
    void reload();
  }

  async function skip(job: Job) {
    await api.POST("/api/jobs/{job_id}/skip", { params: { path: { job_id: job.job_id } } });
    void reload();
  }

  const pending = (data || []).filter((j) => j.status === "awaiting_approval").length;
  return (
    <>
      <div className="spread">
        <h1>Job inbox</h1>
        <div className="row">
          {pending > 0 && <span className="badge info" data-testid="pending-count">{pending} awaiting your approval</span>}
          <button onClick={scout} disabled={scouting} data-testid="scout">{scouting ? "Scouting…" : "Scout now"}</button>
        </div>
      </div>
      <div className="row" style={{ margin: "8px 0 12px" }} role="group" aria-label="Filters">
        {(["all", "approve", "bid", "skip", "risky"] as const).map((f) => (
          <button key={f} aria-pressed={filter === f} className={filter === f ? "primary" : ""} onClick={() => setFilter(f)}>
            {f === "approve" ? "Needs approval" : f[0].toUpperCase() + f.slice(1)}</button>
        ))}
        <input aria-label="Search titles" placeholder="Search titles" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} />
      </div>
      {error && <ErrorState error={error} retry={reload} />}
      {loading && !data ? <Loading lines={6} /> : jobs.length === 0 ? (
        <Empty title="No jobs yet">Saved searches run every 30 minutes. Press <strong>Scout now</strong> to run them immediately.</Empty>
      ) : (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table data-testid="inbox-table">
            <thead><tr><th>Job</th><th>Fit</th><th>Risk</th><th>Action</th><th className="hide-sm">Price</th><th className="hide-sm">Connects</th><th>Status</th><th /></tr></thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.job_id} className="clickable" onClick={() => router.push(`/jobs/${encodeURIComponent(j.job_id)}`)}>
                  <td><Link href={`/jobs/${encodeURIComponent(j.job_id)}`} onClick={(e) => e.stopPropagation()}>{j.title}</Link>
                    <div className="small muted">{j.category} · {j.is_hourly ? "hourly" : `budget ${fmtMoney(j.budget)}`}{j.duplicate_of ? ` · duplicate of ${j.duplicate_of}` : ""}</div></td>
                  <td><FitBar value={j.fit_score} /></td>
                  <td><RiskBadge score={j.risk_score} scam={j.is_scam} flags={j.risk_flags} /></td>
                  <td><ActionBadge action={j.action} /></td>
                  <td className="hide-sm">{fmtMoney(j.price, j.price_unit)}</td>
                  <td className="hide-sm">{j.connects_cost ?? "-"}</td>
                  <td><StatusBadge status={j.status} />
                    {j.status === "awaiting_approval" && <div><Link href={`/studio/${encodeURIComponent(j.job_id)}`} onClick={(e) => e.stopPropagation()}>Review draft →</Link></div>}</td>
                  <td>{j.status !== "skipped" && j.status !== "submitted" && (
                    <button className="small" onClick={(e) => { e.stopPropagation(); void skip(j); }} aria-label={`Skip ${j.title}`}>Skip</button>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
