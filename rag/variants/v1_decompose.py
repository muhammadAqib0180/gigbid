"""V1 (query group, required): one retrieval per extracted requirement, merged round-robin."""

from rag.variants.base import PipelineConfig

VARIANT = PipelineConfig(name="v1_decompose", query="decompose", retriever="dense", chunking="fixed",
                         description="Requirement decomposition: one retrieval per requirement, then merge")
