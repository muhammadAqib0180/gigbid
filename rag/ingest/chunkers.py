"""Chunkers. `fixed` is the V0 baseline; `structured` splits by Markdown heading, code block and
proposal paragraph; `contextual` (V6) prefixes each chunk with a one-line context header."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.ingest.loaders import Doc


@dataclass
class Chunk:
    chunk_id: str
    doc: Doc
    text: str
    index_text: str = ""            # what is embedded / BM25-indexed (may carry a context header)
    meta: dict = field(default_factory=dict)


def fixed(doc: Doc, size: int = 600, overlap: int = 100) -> list[str]:
    t = doc.text
    if len(t) <= size:
        return [t]
    out, i = [], 0
    while i < len(t):
        out.append(t[i : i + size])
        i += size - overlap
    return out


def structured(doc: Doc, max_chars: int = 900) -> list[str]:
    if doc.type in {"case_study", "readme", "cv"}:
        parts = re.split(r"\n(?=#{1,3} )", doc.text)
    elif doc.type == "code":
        parts = re.split(r"\n(?=(?:def |class |async def |export |@|CREATE |SELECT |with DAG))", doc.text)
    elif doc.type == "proposal":
        paras = [p for p in doc.text.split("\n\n") if p.strip()]
        parts = ["\n\n".join(paras[i : i + 2]) for i in range(0, len(paras), 2)]
    else:
        parts = [doc.text]
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        while len(p) > max_chars:
            cut = p.rfind(". ", 0, max_chars)
            cut = cut + 1 if cut > max_chars // 3 else max_chars
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            out.append(p)
    # merge tiny fragments into their neighbour
    merged: list[str] = []
    for p in out:
        if merged and len(p) < 120:
            merged[-1] += "\n" + p
        else:
            merged.append(p)
    return merged or [doc.text[:max_chars]]


def context_header(doc: Doc) -> str:
    bits = [doc.type.replace("_", " ")]
    if doc.title:
        bits.append(f"'{doc.title[:80]}'")
    if doc.project:
        bits.append(f"project {doc.project}")
    if doc.client_industry:
        bits.append(f"{doc.client_industry} client")
    if doc.outcome:
        bits.append(f"outcome {doc.outcome}")
    if doc.skills:
        bits.append("skills: " + ", ".join(doc.skills[:6]))
    return "[" + " | ".join(bits) + "]"


def chunk_docs(docs: list[Doc], strategy: str = "structured", contextual: bool = False) -> list[Chunk]:
    chunks: list[Chunk] = []
    for d in docs:
        pieces = fixed(d) if strategy == "fixed" else structured(d)
        header = context_header(d) if contextual else ""
        for i, p in enumerate(pieces):
            chunks.append(Chunk(chunk_id=f"{d.doc_id}#c{i}", doc=d, text=p, index_text=(header + "\n" + p) if header else p))
    return chunks
