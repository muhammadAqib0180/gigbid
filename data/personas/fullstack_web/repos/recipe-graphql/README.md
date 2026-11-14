# recipe-graphql

GraphQL API for a recipe app (synthetic portfolio repository).

## Stack

- GraphQL
- Node.js
- Prisma
- PostgreSQL

## Setup

```bash
make install
make test
```

## Architecture

The service designed a GraphQL schema with batched resolvers. See `src/` for the pipeline entry points.
