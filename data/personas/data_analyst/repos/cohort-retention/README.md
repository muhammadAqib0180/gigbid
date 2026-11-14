# cohort-retention

Cohort retention analysis (synthetic portfolio repository).

## Stack

- SQL
- cohort analysis
- Looker Studio
- data visualization

## Setup

```bash
make install
make test
```

## Architecture

The service built weekly cohorts and retention curves by acquisition channel. See `src/` for the pipeline entry points.
