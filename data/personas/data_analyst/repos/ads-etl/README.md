# ads-etl

ETL pipeline for advertising platforms (synthetic portfolio repository).

## Stack

- Airflow
- Python
- BigQuery
- ETL

## Setup

```bash
make install
make test
```

## Architecture

The service built daily extract-and-load jobs with schema checks and alerting. See `src/` for the pipeline entry points.
