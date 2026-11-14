# product-recs

Product recommendations for an online store (synthetic portfolio repository).

## Stack

- Python
- recommendation systems
- PyTorch
- implicit feedback

## Setup

```bash
make install
make test
```

## Architecture

The service trained a two-tower model on clicks and purchases and served candidates with a re-ranking step. See `src/` for the pipeline entry points.
