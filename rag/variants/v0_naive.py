"""V0 (baseline, required): fixed 600-char chunks, whole job post as one query, dense top-k cosine."""

from rag.variants.base import PipelineConfig

VARIANT = PipelineConfig(name="v0_naive", query="whole", retriever="dense", chunking="fixed",
                         description="Naive dense: fixed chunks, top-k cosine on the whole job post")
