# anomaly-iot

Sensor anomaly detection for pumping stations (synthetic portfolio repository).

## Stack

- Python
- anomaly detection
- time series
- scikit-learn

## Setup

```bash
make install
make test
```

## Architecture

The service combined seasonal decomposition with isolation forests on vibration and pressure signals. See `src/` for the pipeline entry points.
