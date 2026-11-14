# saas-billing

Subscription billing portal (synthetic portfolio repository).

## Stack

- Next.js
- TypeScript
- Stripe
- PostgreSQL
- Prisma

## Setup

```bash
make install
make test
```

## Architecture

The service built a self-serve billing area with proration. See `src/` for the pipeline entry points.
