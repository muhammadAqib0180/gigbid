"""V5 (indexing): structure-aware chunks; a project's case study, README and code chunks are indexed
separately but vote together and come back as one project."""

from rag.variants.base import PipelineConfig

VARIANT = PipelineConfig(name="v5_multivector", query="whole", retriever="dense", chunking="structured", group_projects=True,
                         description="Multi-vector items: summary/README/code returned as one project")
