# demand-forecast

Demand forecasting for a grocery chain (synthetic portfolio repository).

## Stack

- Python
- time series forecasting
- LightGBM
- pandas

## Setup

```bash
make install
make test
```

## Architecture

The service trained a global gradient-boosting model with holiday and weather features and produced daily forecasts per store and SKU. See `src/` for the pipeline entry points.
