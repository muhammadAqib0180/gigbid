"""V2 (retrieval group, required): BM25 + dense fused with reciprocal rank fusion (k=60).
Targets exact tool names ("Celery", "dbt", "Pinecone") that embeddings blur."""

from rag.variants.base import PipelineConfig

VARIANT = PipelineConfig(name="v2_hybrid", query="whole", retriever="hybrid", chunking="fixed",
                         description="Hybrid BM25 + dense with reciprocal rank fusion")
