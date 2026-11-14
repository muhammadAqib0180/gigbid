"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/http";
import { useEventStream } from "@/lib/hooks";

/** "Marketplace unavailable" banner: polls dependency health and listens for degraded events on the user stream. */
export function DegradedBanner() {
  const [down, setDown] = useState<string | null>(null);
  const [mode, setMode] = useState<string>("");

  useEffect(() => {
    let alive = true;
    const check = async () => {
      const { data } = await api.GET("/api/health/dependencies");
      if (!alive || !data) return;
      setMode(`${data.marketplace_mode} · models: ${data.model_profile}`);
      setDown(data.status === "degraded" ? String((data.marketplace as { detail?: string }).detail || "unreachable") : null);
    };
    void check();
    const t = setInterval(check, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  useEventStream("/api/events/stream", (type, d) => {
    if (type === "degraded") setDown(String(d.detail || "unreachable"));
    if (type === "health" && d.server === "marketplace") setDown(d.ok ? null : String(d.detail || "unreachable"));
  });

  if (!down) return mode ? <p className="small muted" style={{ margin: "0 0 8px" }} data-testid="mode">{mode}</p> : null;
  return (
    <div className="banner warn" role="alert" data-testid="degraded-banner">
      <strong>Marketplace unavailable.</strong> GigBid cannot reach the marketplace right now ({down}). New scouting and submissions are
      queued and will resume automatically when it is back. Nothing is lost and nothing is sent without your approval.
    </div>
  );
}
