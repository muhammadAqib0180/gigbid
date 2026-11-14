"use client";
import type { ReactNode } from "react";
import { pct } from "@/lib/http";

export function Loading({ lines = 4, label = "Loading" }: { lines?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite" aria-label={label}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: Error; retry?: () => void }) {
  const status = (error as { status?: number }).status;
  const text = status === 503 ? "The marketplace is unavailable right now. Your work is queued and will resume automatically." : error.message;
  return (
    <div className="banner bad" role="alert">
      <strong>Something went wrong.</strong> {text} {retry && <button onClick={retry} style={{ marginLeft: 8 }}>Retry</button>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <p style={{ fontWeight: 600, margin: "0 0 4px" }}>{title}</p>
      {children}
    </div>
  );
}

export function FitBar({ value }: { value?: number | null }) {
  if (value == null) return <span className="muted">-</span>;
  return (
    <div className="row" title={`fit ${pct(value)}`}>
      <div className="bar" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)} aria-label="fit score">
        <span style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="small">{pct(value)}</span>
    </div>
  );
}

export function RiskBadge({ score, scam, flags }: { score?: number | null; scam?: boolean; flags?: string[] }) {
  if (score == null) return <span className="muted">-</span>;
  const cls = scam ? "bad" : score >= 0.6 ? "bad" : score >= 0.3 ? "warn" : "ok";
  const label = scam ? "Scam" : score >= 0.6 ? "High risk" : score >= 0.3 ? "Medium risk" : "Low risk";
  return (
    <span className={`badge ${cls}`} title={(flags || []).join(", ")}>
      {label} {pct(score)}
    </span>
  );
}

const STATUS: Record<string, string> = {
  awaiting_approval: "info", submitted: "ok", approved: "ok", skipped: "neutral", watching: "warn", duplicate: "neutral",
  needs_attention: "bad", blocked: "bad", dead_letter: "bad", error: "bad", waiting_marketplace: "warn", queued: "neutral",
  resuming: "info", rejected: "neutral", drafting: "info", analysing: "info", running: "info", finished: "ok", sent: "ok",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${STATUS[status] || "neutral"}`}>{status.replace(/_/g, " ")}</span>;
}

export function ActionBadge({ action }: { action?: string | null }) {
  if (!action) return <span className="muted">-</span>;
  const cls = action === "bid" ? "ok" : action === "watch" ? "warn" : "neutral";
  return <span className={`badge ${cls}`}>{action}</span>;
}
