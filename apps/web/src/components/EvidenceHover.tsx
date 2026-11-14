"use client";
import React, { useState } from "react";

export type ClaimEvidence = { evidence_id: string; title?: string; type?: string; source?: string; snippet?: string };
export type Claim = { claim_id: string; text: string; label: string; score?: number; note?: string; evidence: ClaimEvidence[] };

/** Renders the cover letter; every verified claim is underlined (green supported, amber partly, red unsupported)
 *  and shows the evidence behind it on hover or keyboard focus. */
export function EvidenceHover({ text, claims }: { text: string; claims: Claim[] }) {
  const paragraphs = text.split(/\n\s*\n/).filter((p) => p.trim());
  return (
    <div className="letter" data-testid="proposal-letter">
      {paragraphs.map((p, i) => (
        <p key={i}>{renderWithClaims(p, claims)}</p>
      ))}
    </div>
  );
}

function renderWithClaims(paragraph: string, claims: Claim[]) {
  const parts: (string | React.ReactElement)[] = [];
  let rest = paragraph;
  let k = 0;
  const sorted = claims.filter((c) => c.text && paragraph.includes(c.text));
  while (rest.length) {
    let best: { c: Claim; idx: number } | null = null;
    for (const c of sorted) {
      const idx = rest.indexOf(c.text);
      if (idx >= 0 && (!best || idx < best.idx)) best = { c, idx };
    }
    if (!best) {
      parts.push(rest);
      break;
    }
    if (best.idx > 0) parts.push(rest.slice(0, best.idx));
    parts.push(<ClaimSpan key={k++} claim={best.c} />);
    rest = rest.slice(best.idx + best.c.text.length);
  }
  return parts;
}

function ClaimSpan({ claim }: { claim: Claim }) {
  const [open, setOpen] = useState(false);
  const label = claim.label.replace("_", " ");
  return (
    <span
      className={`claim ${claim.label}`}
      tabIndex={0}
      role="button"
      aria-expanded={open}
      aria-label={`${label} claim; show evidence`}
      data-testid="claim"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
    >
      {claim.text}
      {open && (
        <span className="pop" role="tooltip">
          <strong>{label}</strong> {claim.score != null && <span className="muted">(support {claim.score.toFixed(2)})</span>}
          {claim.note && <div className="muted">{claim.note}</div>}
          {claim.evidence.length === 0 && <div>No evidence linked.</div>}
          {claim.evidence.map((e) => (
            <span key={e.evidence_id} style={{ display: "block", marginTop: 6 }}>
              <span className="badge neutral">{e.type}</span> <strong>{e.title}</strong>
              <span className="mono muted" style={{ display: "block" }}>{e.source}</span>
              <span style={{ display: "block" }}>{(e.snippet || "").slice(0, 260)}…</span>
            </span>
          ))}
        </span>
      )}
    </span>
  );
}
