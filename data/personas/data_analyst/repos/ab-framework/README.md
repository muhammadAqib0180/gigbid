# ab-framework

A/B test analysis framework (synthetic portfolio repository).

## Stack

- statistics
- A/B testing
- Python
- SQL

## Setup

```bash
make install
make test
```

## Architecture

The service wrote a standard analysis notebook with guardrail metrics and sequential testing rules. See `src/` for the pipeline entry points.
