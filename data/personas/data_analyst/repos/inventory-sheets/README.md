# inventory-sheets

Inventory forecasting in Google Sheets (synthetic portfolio repository).

## Stack

- Google Sheets
- forecasting
- Apps Script

## Setup

```bash
make install
make test
```

## Architecture

The service built a reorder model with seasonality and lead times inside the sheet they already used. See `src/` for the pipeline entry points.
