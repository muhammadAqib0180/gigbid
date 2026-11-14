"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ApprovalPanel } from "@/components/ApprovalPanel";
import { Empty, ErrorState, Loading, StatusBadge } from "@/components/ui";
import { useUser } from "@/components/Shell";
import { api, enc } from "@/lib/http";
import { useEventStream, useLoad } from "@/lib/hooks";

/** Proposal studio: the pending approval for one job, read from the LangGraph checkpointer (refresh-safe). */
export default function Studio() {
  const { id } = useParams<{ id: string }>();
  const jobId = decodeURIComponent(id);
  const user = useUser();
  const [done, setDone] = useState<string | null>(null);
  const threadId = user ? `bid:${user.id}:${jobId}` : null;
  const { data, error, loading, reload } = useLoad(async () => {
    if (!threadId) return null;
    const res = await api.GET("/api/approvals/{thread_id}", { params: { path: { thread_id: threadId } } });
    if (res.response.status === 404) return null;
    if (res.error) throw new Error((res.error as { detail?: string }).detail || "failed");
    return res.data ?? null;
  }, [threadId]);
  const job = useLoad(() => api.GET("/api/jobs/{job_id}", { params: { path: { job_id: jobId } } }).then((r) => r.data ?? null), [jobId]);

  useEventStream("/api/events/stream", (type, d) => {
    if ((type === "run_finished" || type === "run_event") && d.thread_id === threadId) {
      if (type === "run_finished") { setDone(null); void reload(); void job.reload(); }
    }
  });

  return (
    <>
      <p className="small"><Link href={`/jobs/${enc(jobId)}`}>← Job detail</Link></p>
      <div className="spread">
        <h1>Proposal studio</h1>
        {job.data && <StatusBadge status={job.data.status} />}
      </div>
      {job.data && <p className="muted">{job.data.title}</p>}
      {done && <div className="banner info" role="status" data-testid="decision-banner">{done}</div>}
      {error && <ErrorState error={error} retry={reload} />}
      {loading && !data ? <Loading lines={8} /> : data ? (
        <ApprovalPanel key={`${data.thread_id}:${(data.payload as { draft?: { version?: number } }).draft?.version}`} threadId={data.thread_id}
          payload={data.payload as Record<string, unknown>} onDone={(m) => { setDone(m); setTimeout(() => { void reload(); void job.reload(); }, 2500); }} />
      ) : (
        <Empty title="Nothing waiting for approval">
          {job.data?.status === "submitted" ? "This proposal was submitted." : "The agents are still working on this job, or it was skipped."}{" "}
          {threadId && <Link href={`/runs/${enc(threadId)}`}>See the agent run</Link>}
        </Empty>
      )}
    </>
  );
}
