"use client";
import { useState } from "react";
import { EvidenceHover, type Claim } from "./EvidenceHover";
import { api, enc, fmtMoney } from "@/lib/http";

type Payload = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

/** Human approval: approve / edit (diffed, saved for style memory, re-checked by Compliance) / reject with reason.
 *  Shows the draft with evidence on hover, Critic + Compliance comments, price rationale and the dry_run preview. */
export function ApprovalPanel({ threadId, payload, onDone }: { threadId: string; payload: Payload; onDone: (msg: string) => void }) {
  const isProposal = payload.type === "proposal_approval";
  const original: string = isProposal ? payload.draft?.cover_letter ?? "" : payload.draft?.reply_text ?? "";
  const [mode, setMode] = useState<"view" | "edit" | "reject">("view");
  const [text, setText] = useState(original);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [regenIdx, setRegenIdx] = useState<number | null>(null);

  async function send(action: "approve" | "edit" | "reject") {
    setBusy(true);
    setErr(null);
    const body = action === "edit" ? { action, edited_text: text } : action === "reject" ? { action, reason } : { action };
    const { error, response } = await api.POST("/api/approvals/{thread_id}", { params: { path: { thread_id: threadId } }, body });
    setBusy(false);
    if (error) {
      setErr((error as { detail?: string }).detail || `failed (${response.status})`);
      return;
    }
    onDone(action === "approve" ? "Approved - submitting through the marketplace port." :
      action === "edit" ? "Edit saved - Compliance is re-checking it; the draft will come back for approval." : "Rejected.");
  }

  async function regenerate(i: number) {
    setRegenIdx(i);
    const res = await fetch(`/api/proposals/${enc(threadId)}/regenerate`, {
      method: "POST", credentials: "include", headers: { "content-type": "application/json" },
      body: JSON.stringify({ paragraph_index: i, text }),
    });
    setRegenIdx(null);
    if (!res.ok) return setErr("could not regenerate paragraph");
    const data = await res.json();
    const paras = text.split(/\n\s*\n/).filter((p) => p.trim());
    paras[i] = data.text;
    setText(paras.join("\n\n"));
  }

  const critiques: Payload[] = payload.critiques || [];
  const lastCrit = critiques[critiques.length - 1];
  const compliance: Payload = payload.compliance || {};
  const preview: Payload = payload.preview || {};
  const verification: Payload = payload.verification || {};

  return (
    <section aria-label="Approval" data-testid="approval-panel">
      <div className="grid2">
        <div className="card">
          <div className="spread">
            <h2 style={{ margin: 0 }}>{isProposal ? `Draft v${payload.draft?.version}` : `Suggested reply (${payload.intent?.intent})`}</h2>
            {isProposal && <span className="badge info">strategy: {payload.draft?.strategy}</span>}
          </div>
          {mode === "edit" ? (
            <>
              <label htmlFor="edit-text">Edit the draft (your edits are diffed and may teach GigBid your style)</label>
              <textarea id="edit-text" value={text} onChange={(e) => setText(e.target.value)} data-testid="edit-text" />
              {isProposal && (
                <div className="row small" style={{ marginTop: 6 }}>
                  Regenerate paragraph:
                  {text.split(/\n\s*\n/).filter((p) => p.trim()).map((_, i) => (
                    <button key={i} className="small" disabled={regenIdx !== null} onClick={() => regenerate(i)}>
                      {regenIdx === i ? "…" : `¶${i + 1}`}
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : isProposal ? (
            <EvidenceHover text={original} claims={(payload.claims || []) as Claim[]} />
          ) : (
            <p style={{ whiteSpace: "pre-wrap" }}>{original}</p>
          )}
          {isProposal && (payload.draft?.screening_answers || []).length > 0 && (
            <>
              <h3>Screening answers</h3>
              {(payload.draft.screening_answers as Payload[]).map((a, i) => (
                <p key={i} className="small"><strong>{a.question}</strong><br />{a.answer}</p>
              ))}
            </>
          )}
          {!isProposal && (payload.slots || []).length > 0 && (
            <p className="small">Interview slots offered: {(payload.slots as Payload[]).map((s) => s.start.replace("T", " ")).join(" · ")}</p>
          )}
          {!isProposal && <p className="small muted">Client wrote: “{payload.client_message?.text}”</p>}
        </div>

        <div>
          {isProposal && (
            <div className="card" data-testid="dry-run">
              <h3 style={{ marginTop: 0 }}>What will be sent (dry run)</h3>
              <p className="small">Bid {fmtMoney(payload.price?.amount, payload.price?.unit)} · costs <strong>{preview.connects_cost ?? payload.price?.connects_cost} Connects</strong>
                {preview.balance_before != null && <> · balance {preview.balance_before} → {Number(preview.balance_before) - Number(preview.connects_cost || 0)}</>}</p>
              {(preview.warnings || []).map((w: string) => <p key={w} className="small muted">⚠ {w}</p>)}
              <h3>Price rationale</h3>
              <ul className="small">{(payload.price?.rationale || []).map((r: string) => <li key={r}>{r}</li>)}</ul>
            </div>
          )}
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Checks</h3>
            {isProposal && (
              <p className="small">Claim verification: {verification.total_claims ?? 0} claims · unsupported {verification.unsupported_before ?? 0} → {verification.unsupported_after ?? 0}
                {(verification.removed || []).length > 0 && <> · removed: “{(verification.removed as string[]).join("”, “").slice(0, 160)}”</>}</p>
            )}
            {lastCrit && <p className="small"><span className={`badge ${lastCrit.verdict === "pass" ? "ok" : "warn"}`}>Critic: {lastCrit.verdict}</span>{" "}
              {(lastCrit.reasons || []).join("; ") || "no issues"}</p>}
            <p className="small"><span className={`badge ${compliance.allowed === false ? "bad" : "ok"}`}>Compliance: {compliance.allowed === false ? "blocked" : "ok"}</span>{" "}
              {(compliance.redactions || []).map((r: Payload) => `${r.kind}${r.original ? ` (“${String(r.original).slice(0, 40)}”)` : ""}`).join(", ") || "no changes"}</p>
            {isProposal && payload.risk && <p className="small">Risk {Math.round((payload.risk.score || 0) * 100)}% · {(payload.risk.flags || []).join(", ") || "no flags"}</p>}
          </div>
        </div>
      </div>

      {err && <div className="banner bad" role="alert">{err}</div>}
      {mode === "reject" && (
        <div className="card">
          <label htmlFor="reason">Reason for rejecting (used in analytics)</label>
          <input id="reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. budget too low for this scope" data-testid="reject-reason" />
        </div>
      )}
      <div className="row" style={{ marginTop: 12 }}>
        {mode === "view" && <>
          <button className="primary" disabled={busy} onClick={() => send("approve")} data-testid="approve">Approve & {isProposal ? "submit" : "send"}</button>
          <button disabled={busy} onClick={() => setMode("edit")} data-testid="edit">Edit</button>
          <button className="danger" disabled={busy} onClick={() => setMode("reject")} data-testid="reject">Reject</button>
        </>}
        {mode === "edit" && <>
          <button className="primary" disabled={busy || !text.trim() || text === original} onClick={() => send("edit")} data-testid="save-edit">Save edit & re-check</button>
          <button onClick={() => { setMode("view"); setText(original); }}>Cancel</button>
        </>}
        {mode === "reject" && <>
          <button className="danger" disabled={busy || !reason.trim()} onClick={() => send("reject")} data-testid="confirm-reject">Confirm reject</button>
          <button onClick={() => setMode("view")}>Cancel</button>
        </>}
        <span className="small muted">Nothing is sent until you approve. Live Upwork mode only creates drafts you confirm on Upwork.</span>
      </div>
    </section>
  );
}
