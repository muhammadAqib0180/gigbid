"""V3 (retrieval group, required): cross-encoder re-ranking of the top-30 dense candidates."""

from rag.variants.base import PipelineConfig

VARIANT = PipelineConfig(name="v3_rerank", query="whole", retriever="dense", rerank=True, chunking="fixed",
                         description="Cross-encoder reranking (ms-marco MiniLM, CPU)")
