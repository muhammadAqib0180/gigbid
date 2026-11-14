"use client";
import { useEffect, useState } from "react";
import { Empty, ErrorState, Loading } from "@/components/ui";
import { api, must, type Schemas } from "@/lib/http";
import { useLoad } from "@/lib/hooks";

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function SettingsPage() {
  const s = useLoad(() => must(api.GET("/api/settings")), []);
  const searches = useLoad(() => must(api.GET("/api/saved-searches")), []);
  const mem = useLoad(() => must(api.GET("/api/memory")), []);
  const accounts = useLoad(() => must(api.GET("/api/accounts")), []);
  const [form, setForm] = useState<Schemas["SettingsOut"] | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [newSearch, setNewSearch] = useState({ name: "", query: "" });
  useEffect(() => { if (s.data) setForm(s.data); }, [s.data]);

  async function save() {
    if (!form) return;
    await api.PUT("/api/settings", { body: { hourly_rate_usd: form.hourly_rate_usd, min_hourly_usd: form.min_hourly_usd, min_fixed_usd: form.min_fixed_usd,
      weekly_connects: form.weekly_connects, autonomy: form.autonomy as any, max_tokens_per_job: form.max_tokens_per_job, proposal_strategy: form.proposal_strategy as any } });
    setSaved("Saved.");
  }
  async function addSearch() {
    if (!newSearch.name) return;
    await api.POST("/api/saved-searches", { body: { ...newSearch, skills: [], interval_minutes: 30, enabled: true } });
    setNewSearch({ name: "", query: "" });
    void searches.reload();
  }
  async function forget(ns: string, key: string) {
    await api.DELETE("/api/memory/{namespace}/{key}", { params: { path: { namespace: ns, key } } });
    void mem.reload();
  }
  async function connectUpwork() {
    const r = await fetch("/api/accounts/upwork/connect", { method: "POST", credentials: "include" });
    const d = await r.json();
    if (d.authorization_url) window.location.href = d.authorization_url;
    else setSaved(d.detail || "Upwork connection failed");
  }

  if (s.error) return <ErrorState error={s.error} retry={s.reload} />;
  if (s.loading || !form) return <Loading lines={6} />;
  const set = (k: keyof Schemas["SettingsOut"], v: any) => setForm({ ...form, [k]: v });
  return (
    <>
      <h1>Settings</h1>
      <div className="grid2">
        <section className="card" aria-label="Autonomy and budgets">
          <h2 style={{ marginTop: 0 }}>Autonomy and budgets</h2>
          <label htmlFor="autonomy">Autonomy</label>
          <select id="autonomy" value={form.autonomy} onChange={(e) => set("autonomy", e.target.value)}>
            <option value="suggest">Suggest only (I decide everything)</option>
            <option value="auto_skip_low_fit">Auto-skip low-fit and scam jobs (never auto-send)</option>
          </select>
          <div className="grid2">
            <div><label htmlFor="rate">Hourly rate</label><input id="rate" type="number" value={form.hourly_rate_usd} onChange={(e) => set("hourly_rate_usd", +e.target.value)} /></div>
            <div><label htmlFor="mh">Min hourly</label><input id="mh" type="number" value={form.min_hourly_usd} onChange={(e) => set("min_hourly_usd", +e.target.value)} /></div>
            <div><label htmlFor="mf">Min fixed</label><input id="mf" type="number" value={form.min_fixed_usd} onChange={(e) => set("min_fixed_usd", +e.target.value)} /></div>
            <div><label htmlFor="wc">Weekly Connects</label><input id="wc" type="number" value={form.weekly_connects} onChange={(e) => set("weekly_connects", +e.target.value)} /></div>
            <div><label htmlFor="tb">Token budget per job</label><input id="tb" type="number" value={form.max_tokens_per_job} onChange={(e) => set("max_tokens_per_job", +e.target.value)} /></div>
            <div><label htmlFor="ps">Proposal strategy</label>
              <select id="ps" value={form.proposal_strategy} onChange={(e) => set("proposal_strategy", e.target.value)}>
                <option value="evidence_first">Evidence first</option><option value="question_first">Question first</option><option value="ab">A/B test both</option>
              </select></div>
          </div>
          <div className="row" style={{ marginTop: 10 }}><button className="primary" onClick={save}>Save</button>{saved && <span className="small" role="status">{saved}</span>}</div>
        </section>
        <section className="card" aria-label="Connected accounts">
          <h2 style={{ marginTop: 0 }}>Connected accounts</h2>
          {accounts.data ? (
            <ul className="small">
              <li>GigSim: connected as <strong>{(accounts.data as any).gigsim.account}</strong></li>
              <li>Upwork (official MCP, OAuth 2.1): {(accounts.data as any).upwork.connected ? "connected" : <button className="small" onClick={connectUpwork}>Connect</button>}
                <span className="muted"> - live mode only creates drafts you confirm on Upwork.</span></li>
              <li>GitHub MCP (repo ingestion): {(accounts.data as any).github.connected ? "configured" : "not configured (set GITHUB_PAT)"}</li>
            </ul>) : <Loading lines={2} />}
          <p className="small muted">Marketplace mode: {form.marketplace_mode} · persona: {form.persona_id} · account: {form.account_id}</p>
          <h2>Saved searches</h2>
          {(searches.data || []).map((x) => (
            <div key={x.id} className="spread small" style={{ borderBottom: "1px solid var(--line)", padding: "4px 0" }}>
              <span><strong>{x.name}</strong> “{x.query}” · every {x.interval_minutes} min</span>
              <button className="small" onClick={async () => { await api.DELETE("/api/saved-searches/{search_id}", { params: { path: { search_id: x.id } } }); void searches.reload(); }}>Remove</button>
            </div>))}
          <div className="row" style={{ marginTop: 8 }}>
            <input aria-label="Search name" placeholder="Name" value={newSearch.name} onChange={(e) => setNewSearch({ ...newSearch, name: e.target.value })} style={{ maxWidth: 160 }} />
            <input aria-label="Keywords" placeholder="Keywords" value={newSearch.query} onChange={(e) => setNewSearch({ ...newSearch, query: e.target.value })} style={{ maxWidth: 200 }} />
            <button onClick={addSearch}>Add</button>
          </div>
        </section>
      </div>
      <section className="card" style={{ marginTop: 12 }} aria-label="Memory viewer">
        <h2 style={{ marginTop: 0 }}>What GigBid has learned</h2>
        <p className="small muted">Style rules are promoted only after the same edit pattern appears in 3 different proposals (or you ask). Outcome insights need 5+ outcomes in a category. You can delete anything.</p>
        {mem.error && <ErrorState error={mem.error} retry={mem.reload} />}
        {mem.data && (
          <div className="grid3">
            {(["style", "style_candidates", "outcome"] as const).map((ns) => (
              <div key={ns}>
                <h3>{ns === "style" ? "Style rules (promoted)" : ns === "style_candidates" ? "Style candidates" : "Outcome memory"}</h3>
                {(mem.data as any)[ns].length === 0 ? <Empty title="Nothing yet" /> : (mem.data as any)[ns].map((m: any) => (
                  <div key={m.key} className="kcard" data-testid={`memory-${ns}`}>
                    <div>{m.value.rule || m.value.insight || m.key}</div>
                    <div className="muted">{ns === "style_candidates" ? `${Object.keys(m.value.proposals || {}).length} proposal(s)` : ns === "outcome" ? `${Object.keys(m.value.stats?.proposals || {}).length} outcomes` : m.value.promotion_rule}</div>
                    <button className="small" onClick={() => forget(ns, m.key)} aria-label={`Delete ${m.key}`}>Delete</button>
                  </div>))}
              </div>))}
          </div>)}
      </section>
    </>
  );
}
