# aws-containers

Containerised deployment on AWS (synthetic portfolio repository).

## Stack

- Docker
- AWS ECS
- Terraform
- CI/CD

## Setup

```bash
make install
make test
```

## Architecture

The service containerised the app. See `src/` for the pipeline entry points.
