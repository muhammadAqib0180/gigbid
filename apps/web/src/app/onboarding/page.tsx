"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/http";

const PERSONAS = [
  ["ai_ml_engineer", "AI/ML engineer", "LLM apps, RAG, forecasting, computer vision"],
  ["fullstack_web", "Full-stack web developer", "Next.js, Node, Django, payments"],
  ["data_analyst", "Data analyst", "SQL, dashboards, dbt, experimentation"],
] as const;
const DEFAULT_SEARCH: Record<string, [string, string, string]> = {
  ai_ml_engineer: ["LLM / RAG work", "llm", "ml_ai"], fullstack_web: ["React apps", "react", "web_dev"], data_analyst: ["Dashboards", "dashboard", "data_analytics"],
};

export default function Onboarding() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [profile, setProfile] = useState<"persona" | "own">("persona");
  const [persona, setPersona] = useState("ai_ml_engineer");
  const [market, setMarket] = useState<"gigsim" | "upwork_live">("gigsim");
  const [rate, setRate] = useState(40);
  const [minHourly, setMinHourly] = useState(30);
  const [minFixed, setMinFixed] = useState(250);
  const [connects, setConnects] = useState(80);
  const [query, setQuery] = useState(DEFAULT_SEARCH.ai_ml_engineer[1]);
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function finish() {
    setBusy(true);
    setErr(null);
    const [name, , category] = DEFAULT_SEARCH[persona];
    const { error } = await api.POST("/api/onboarding", {
      body: {
        profile, persona_id: persona, marketplace_mode: market, account_id: persona, hourly_rate_usd: rate, min_hourly_usd: minHourly,
        min_fixed_usd: minFixed, weekly_connects: connects,
        saved_searches: [{ name, query, category, skills: [], interval_minutes: 30, enabled: true }],
      },
    });
    if (error) {
      setBusy(false);
      return setErr((error as { detail?: string }).detail || "Could not save");
    }
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      await fetch("/api/portfolio/upload", { method: "POST", body: fd, credentials: "include" });
    }
    await api.POST("/api/scout");
    router.replace("/inbox");
  }

  return (
    <div style={{ maxWidth: 680, margin: "4vh auto" }}>
      <h1>Set up GigBid</h1>
      <p className="muted">Step {step} of 3</p>
      {step === 1 && (
        <fieldset className="card">
          <legend>Whose portfolio should GigBid use?</legend>
          <label><input type="radio" name="p" checked={profile === "persona"} onChange={() => setProfile("persona")} style={{ width: "auto" }} /> A ready-made persona (synthetic demo data)</label>
          {profile === "persona" && PERSONAS.map(([id, label, desc]) => (
            <label key={id} style={{ marginLeft: 22 }}>
              <input type="radio" name="persona" checked={persona === id} style={{ width: "auto" }}
                onChange={() => { setPersona(id); setQuery(DEFAULT_SEARCH[id][1]); }} data-testid={`persona-${id}`} /> <strong>{label}</strong> - {desc}
            </label>
          ))}
          <label><input type="radio" name="p" checked={profile === "own"} onChange={() => setProfile("own")} style={{ width: "auto" }} /> My own profile (upload CV / case studies)</label>
          {profile === "own" && (
            <div style={{ marginLeft: 22 }}>
              <label htmlFor="upload">Portfolio file (Markdown, text or PDF)</label>
              <input id="upload" type="file" accept=".md,.txt,.pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            </div>
          )}
          <div className="row" style={{ marginTop: 12 }}><button className="primary" onClick={() => setStep(2)} data-testid="next-1">Next</button></div>
        </fieldset>
      )}
      {step === 2 && (
        <fieldset className="card">
          <legend>Marketplace</legend>
          <label><input type="radio" checked={market === "gigsim"} onChange={() => setMarket("gigsim")} style={{ width: "auto" }} /> GigSim (simulator - safe, used for grading)</label>
          <label><input type="radio" checked={market === "upwork_live"} onChange={() => setMarket("upwork_live")} style={{ width: "auto" }} /> Upwork (official MCP server, OAuth; drafts only - connect in Settings)</label>
          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={() => setStep(1)}>Back</button><button className="primary" onClick={() => setStep(3)} data-testid="next-2">Next</button>
          </div>
        </fieldset>
      )}
      {step === 3 && (
        <fieldset className="card">
          <legend>Rates, budget and filters</legend>
          <div className="grid2">
            <div><label htmlFor="rate">Hourly rate (USD)</label><input id="rate" type="number" min={1} value={rate} onChange={(e) => setRate(+e.target.value)} /></div>
            <div><label htmlFor="minh">Minimum hourly (USD)</label><input id="minh" type="number" min={1} value={minHourly} onChange={(e) => setMinHourly(+e.target.value)} /></div>
            <div><label htmlFor="minf">Minimum fixed-price job (USD)</label><input id="minf" type="number" min={0} value={minFixed} onChange={(e) => setMinFixed(+e.target.value)} /></div>
            <div><label htmlFor="conn">Weekly Connects budget</label><input id="conn" type="number" min={0} value={connects} onChange={(e) => setConnects(+e.target.value)} /></div>
          </div>
          <label htmlFor="q">Saved search keywords (runs every 30 minutes)</label>
          <input id="q" value={query} onChange={(e) => setQuery(e.target.value)} />
          {err && <div className="banner bad" role="alert" style={{ marginTop: 10 }}>{err}</div>}
          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={() => setStep(2)}>Back</button>
            <button className="primary" disabled={busy} onClick={finish} data-testid="finish-onboarding">{busy ? "Setting up…" : "Finish and scout jobs"}</button>
          </div>
        </fieldset>
      )}
    </div>
  );
}
