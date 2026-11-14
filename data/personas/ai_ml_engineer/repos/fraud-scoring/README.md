# fraud-scoring

Real-time transaction fraud scoring (synthetic portfolio repository).

## Stack

- Python
- XGBoost
- FastAPI
- feature engineering

## Setup

```bash
make install
make test
```

## Architecture

The service engineered velocity and device features and served the model behind a low-latency API. See `src/` for the pipeline entry points.
