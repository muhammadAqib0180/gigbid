# ticket-router

Support ticket routing classifier (synthetic portfolio repository).

## Stack

- Hugging Face Transformers
- PyTorch
- fine-tuning
- Python

## Setup

```bash
make install
make test
```

## Architecture

The service fine-tuned a compact transformer on 80. See `src/` for the pipeline entry points.
