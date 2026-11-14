---
id: case-public-api
type: case_study
project: public-api
client_industry: fintech
date: 2024-03
skills: [Node.js, TypeScript, OpenAPI, PostgreSQL]
synthetic: true
---

# Public REST API with rate limiting

**Client:** a fintech company (anonymised, synthetic)  
**Year:** 2024

## The problem

The client's partners integrated through CSV files emailed every night.

## What I did

I designed a versioned API with keys, quotas and generated documentation. The work used Node.js, TypeScript, OpenAPI and PostgreSQL. An in-memory cache sits in front of the database for hot lookups. Partners authenticate with signed, short-lived access tokens.

## Results

- 99.95% uptime over six months.
- 14 partners integrated.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
