"use client";
import Link from "next/link";
import { Empty, ErrorState, Loading } from "@/components/ui";
import { api, enc, fmtMoney, must } from "@/lib/http";
import { useEventStream, useLoad } from "@/lib/hooks";

/** Kanban: drafted -> submitted -> viewed -> replied -> interview -> hired / lost. Cards move on marketplace events. */
export default function Pipeline() {
  const { data, error, loading, reload } = useLoad(() => must(api.GET("/api/pipeline")), []);
  useEventStream("/api/events/stream", (type) => {
    if (type === "pipeline_updated" || type === "run_finished") void reload();
  });
  if (error) return <ErrorState error={error} retry={reload} />;
  if (loading || !data) return <Loading lines={5} />;
  return (
    <>
      <h1>Pipeline</h1>
      {data.cards.length === 0 ? <Empty title="No proposals yet">Drafts appear here once the agents write one for a job you can bid on.</Empty> : (
        <div className="kanban" data-testid="kanban">
          {data.stages.map((st) => {
            const cards = data.cards.filter((c) => c.stage === st);
            return (
              <section className="col" key={st} aria-label={`${st} (${cards.length})`}>
                <h3>{st} <span className="muted">({cards.length})</span></h3>
                {cards.map((c) => (
                  <article className="kcard" key={c.id}>
                    <Link href={c.stage === "drafted" ? `/studio/${enc(c.job_id)}` : `/jobs/${enc(c.job_id)}`}>{c.title}</Link>
                    <div className="muted">{c.category} · {fmtMoney(c.bid_amount)} · {c.connects_spent} Connects</div>
                    <div className="muted">strategy: {c.strategy}</div>
                    {c.marketplace_thread_id && <Link href={`/messages?thread=${enc(c.marketplace_thread_id)}`}>Messages →</Link>}
                  </article>
                ))}
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
