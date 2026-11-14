# public-api

Public REST API with rate limiting (synthetic portfolio repository).

## Stack

- Node.js
- TypeScript
- OpenAPI
- PostgreSQL

## Setup

```bash
make install
make test
```

## Architecture

The service designed a versioned API with keys. See `src/` for the pipeline entry points.
