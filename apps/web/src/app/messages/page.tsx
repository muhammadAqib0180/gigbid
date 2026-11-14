"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ApprovalPanel } from "@/components/ApprovalPanel";
import { Empty, ErrorState, Loading, StatusBadge } from "@/components/ui";
import { api, must } from "@/lib/http";
import { useEventStream, useLoad } from "@/lib/hooks";

function MessagesInner() {
  const params = useSearchParams();
  const [selected, setSelected] = useState<string | null>(params.get("thread"));
  const list = useLoad(() => must(api.GET("/api/messages")), []);
  const detail = useLoad(async () => (selected ? must(api.GET("/api/messages/{mthread}", { params: { path: { mthread: selected } } })) : null), [selected]);
  const [note, setNote] = useState<string | null>(null);
  useEventStream("/api/events/stream", (type) => {
    if (type === "run_finished" || type === "pipeline_updated") { void list.reload(); void detail.reload(); }
  });

  async function draft() {
    if (!selected) return;
    await api.POST("/api/messages/{mthread}/draft", { params: { path: { mthread: selected } } });
    setNote("Drafting a reply…");
  }

  return (
    <>
      <h1>Messages</h1>
      <div className="grid2" style={{ gridTemplateColumns: "minmax(220px, 1fr) 2fr" }}>
        <section className="card" aria-label="Threads">
          {list.error && <ErrorState error={list.error} retry={list.reload} />}
          {list.loading && !list.data ? <Loading /> : (list.data || []).length === 0 ? <Empty title="No client threads yet">Replies to your proposals show up here.</Empty> : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {(list.data || []).map((c) => (
                <li key={c.marketplace_thread_id}>
                  <button style={{ width: "100%", textAlign: "left", marginBottom: 6 }} aria-pressed={selected === c.marketplace_thread_id}
                    onClick={() => { setSelected(c.marketplace_thread_id); setNote(null); }}>
                    <strong>{c.title || c.marketplace_thread_id}</strong><br />
                    <span className="small"><StatusBadge status={c.status} /> {c.intent && <span className="badge neutral">{c.intent.replace("_", " ")}</span>}</span>
                  </button>
                </li>))}
            </ul>)}
        </section>
        <section aria-label="Conversation">
          {!selected ? <Empty title="Pick a thread" /> : detail.error ? <ErrorState error={detail.error} retry={detail.reload} /> :
            detail.loading && !detail.data ? <Loading /> : detail.data && (
              <>
                <div className="card">
                  {detail.data.messages.map((m: Record<string, unknown>) => (
                    <p key={String(m.message_id)} style={{ textAlign: m.sender === "client" ? "left" : "right" }}>
                      <span className={`badge ${m.sender === "client" ? "neutral" : "info"}`}>{String(m.sender)}</span><br />{String(m.text)}</p>
                  ))}
                  {!detail.data.pending && <button onClick={draft}>Draft a reply</button>}
                  {note && <p className="small muted" role="status">{note}</p>}
                </div>
                {detail.data.pending && detail.data.conversation && (
                  <ApprovalPanel threadId={detail.data.conversation.graph_thread_id} payload={detail.data.pending as Record<string, unknown>}
                    onDone={(m) => { setNote(m); setTimeout(() => { void detail.reload(); void list.reload(); }, 2500); }} />)}
              </>)}
        </section>
      </div>
    </>
  );
}

export default function Messages() {
  return <Suspense fallback={<Loading />}><MessagesInner /></Suspense>;
}
