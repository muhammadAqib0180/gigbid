# dbt-warehouse

Modern data stack migration (synthetic portfolio repository).

## Stack

- dbt
- Snowflake
- SQL
- Fivetran

## Setup

```bash
make install
make test
```

## Architecture

The service loaded sources into Snowflake and rebuilt the metrics layer as tested SQL models. See `src/` for the pipeline entry points.
