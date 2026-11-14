# legal-ner

Contract clause extraction (synthetic portfolio repository).

## Stack

- NLP
- spaCy
- Hugging Face Transformers
- Python

## Setup

```bash
make install
make test
```

## Architecture

The service built a clause classifier and entity extractor and a review screen that highlights each clause. See `src/` for the pipeline entry points.
