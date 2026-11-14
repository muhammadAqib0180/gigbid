# e2e-ci

End-to-end test suite and CI pipeline (synthetic portfolio repository).

## Stack

- Playwright
- GitHub Actions
- TypeScript
- Jest

## Setup

```bash
make install
make test
```

## Architecture

The service wrote critical-path browser tests and gated merges on them. See `src/` for the pipeline entry points.
