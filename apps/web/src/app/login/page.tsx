"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/http";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const res = mode === "login"
      ? await api.POST("/api/auth/login", { body: { email, password } })
      : await api.POST("/api/auth/signup", { body: { email, password, display_name: name } });
    setBusy(false);
    if (res.error || !res.data) {
      setErr((res.error as { detail?: string })?.detail || "Could not sign in");
      return;
    }
    router.replace(res.data.onboarded ? "/inbox" : "/onboarding");
  }

  return (
    <div style={{ maxWidth: 420, margin: "8vh auto" }}>
      <h1>◆ GigBid</h1>
      <p className="muted">A team of agents finds jobs, checks them for scams, writes proposals grounded in your portfolio - and waits for your approval before anything is sent.</p>
      <form className="card" onSubmit={submit} aria-label={mode === "login" ? "Sign in" : "Create account"}>
        <div className="tabs" role="tablist">
          <button type="button" role="tab" aria-selected={mode === "login"} onClick={() => setMode("login")}>Sign in</button>
          <button type="button" role="tab" aria-selected={mode === "signup"} onClick={() => setMode("signup")}>Create account</button>
        </div>
        {mode === "signup" && (<><label htmlFor="name">Name</label><input id="name" value={name} onChange={(e) => setName(e.target.value)} /></>)}
        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <label htmlFor="password">Password</label>
        <input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={mode === "signup" ? 8 : undefined}
          value={password} onChange={(e) => setPassword(e.target.value)} />
        {err && <div className="banner bad" role="alert" style={{ marginTop: 10 }}>{err}</div>}
        <button className="primary" style={{ marginTop: 14, width: "100%" }} disabled={busy} type="submit">
          {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>
      <p className="small muted">Reviewers: use the credentials from the private submission comment.</p>
    </div>
  );
}
