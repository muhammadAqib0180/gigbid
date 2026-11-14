# price-optimisation

Dynamic pricing model for a travel site (synthetic portfolio repository).

## Stack

- Python
- scikit-learn
- Bayesian optimisation
- pandas

## Setup

```bash
make install
make test
```

## Architecture

The service modelled demand elasticity per route and season and searched price points within business limits. See `src/` for the pipeline entry points.
