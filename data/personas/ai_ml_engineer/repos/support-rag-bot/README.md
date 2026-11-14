# support-rag-bot

Retrieval-augmented support assistant (synthetic portfolio repository).

## Stack

- Python
- LangChain
- RAG
- OpenAI API
- FastAPI

## Setup

```bash
make install
make test
```

## Architecture

The service chunked the docs by heading. See `src/` for the pipeline entry points.
