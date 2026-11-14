# field-pwa

Offline-first PWA for field inspectors (synthetic portfolio repository).

## Stack

- React
- PWA
- IndexedDB
- Firebase

## Setup

```bash
make install
make test
```

## Architecture

The service built an installable app that stores inspections locally and syncs when back online. See `src/` for the pipeline entry points.
