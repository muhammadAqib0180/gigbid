"""V4 (ranking): boost evidence from proposals that won or got replies, and projects those proposals cited."""

from rag.variants.base import PipelineConfig

VARIANT = PipelineConfig(name="v4_outcome", query="whole", retriever="dense", outcome_boost=True, chunking="fixed",
                         description="Outcome-aware ranking from past proposal results")
