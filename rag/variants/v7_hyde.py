"""V7 (query): HyDE - retrieve with a hypothetical ideal proposal paragraph written for the job."""

from __future__ import annotations

from agent import llm
from agent.requirements import extract_requirements
from agent.safety import wrap_untrusted
from rag.variants.base import PipelineConfig

VARIANT = PipelineConfig(name="v7_hyde", query="hyde", retriever="dense", chunking="fixed",
                         description="HyDE: retrieve with a hypothetical ideal proposal for the job")


async def hypothetical_proposal(job: dict) -> tuple[str, dict]:
    reqs = extract_requirements(job)

    def heuristic() -> str:
        skills = ", ".join(s for r in reqs for s in r.skills)[:200]
        return (f"I have delivered {job.get('title', 'this kind of project')} before. In a similar project I used {skills} "
                f"to {reqs[0].text if reqs else 'deliver the result'} and measured the outcome with the client.")

    res = await llm.text("hyde", "hyde", {"job": wrap_untrusted("job_post", f"{job.get('title')}\n{job.get('description', '')[:1500]}")},
                         heuristic=heuristic)
    return str(res.value), res.usage
