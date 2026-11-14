# churn-predictor

Customer churn prediction for a telecom operator (synthetic portfolio repository).

## Stack

- Python
- scikit-learn
- XGBoost
- pandas
- model evaluation

## Setup

```bash
make install
make test
```

## Architecture

The service built a gradient-boosted classifier on 14 months of usage and billing data. See `src/` for the pipeline entry points.
