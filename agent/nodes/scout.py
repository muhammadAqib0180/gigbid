"""Scout: runs saved searches through the marketplace port, de-duplicates (exact id + near-duplicate reposts)
and returns the new jobs to queue. Runs in the worker on each saved search's schedule (E1); the bid graph's
`scout` node is the hand-in point that loads the job by id."""

from __future__ import annotations

import re

from agent.marketplace_port import McpMarketplacePort
from agent.nodes.common import gateway, node
from agent.safety import neutralize

_W = re.compile(r"[a-z0-9]+")


def fingerprint(job: dict) -> set[str]:
    title = re.sub(r"\((repost|updated)\)|\[updated\]|- urgent", "", (job.get("title") or "").lower())
    toks = _W.findall(title + " " + (job.get("description") or "")[:400].lower())
    return {" ".join(toks[i : i + 3]) for i in range(max(1, len(toks) - 2))}


def is_duplicate(job: dict, recent: list[dict], threshold: float = 0.8) -> str | None:
    fp = fingerprint(job)
    for r in recent:
        if r.get("job_id") == job.get("job_id"):
            return r["job_id"]
        other = r.get("_fp") or fingerprint(r)
        inter = len(fp & other)
        if fp and other and inter / len(fp | other) >= threshold:
            return r["job_id"]
    return None


async def scout_search(gw, search: dict, recent: list[dict]) -> tuple[list[dict], list[dict]]:
    """Returns (new_jobs, duplicates). `recent` = jobs already seen by this user (id + text)."""
    port = McpMarketplacePort(gw, "scout")
    jobs = await port.search_jobs(search.get("query", ""), category=search.get("category"), skills=search.get("skills") or None,
                                  min_budget=search.get("min_budget"), since_minutes=search.get("since_minutes"),
                                  limit=int(search.get("limit", 20)))
    new, dups = [], []
    seen = list(recent)
    for j in jobs:
        dup = is_duplicate(j, seen)
        if dup:
            dups.append({**j, "duplicate_of": dup})
        else:
            new.append(j)
            seen.append({**j, "_fp": fingerprint(j)})
    return new, dups


@node("scout")
async def scout_intake(state, config, store):
    job = state.get("job")
    if not job or not job.get("description"):
        job = await McpMarketplacePort(gateway(state), "scout").get_job(state["job_id"])
    job = {**job, "description": neutralize(job.get("description", ""))}
    return {"job": job, "job_id": job["job_id"], "status": "analysing", "status_reason": "",
            "_summary": f"job {job['job_id']}: {job.get('title', '')[:60]}"}
