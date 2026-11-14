---
id: case-e2e-ci
type: case_study
project: e2e-ci
client_industry: B2B SaaS
date: 2025-04
skills: [Playwright, GitHub Actions, TypeScript, Jest]
synthetic: true
---

# End-to-end test suite and CI pipeline

**Client:** a B2B SaaS company (anonymised, synthetic)  
**Year:** 2025

## The problem

The client's releases regularly broke the checkout flow.

## What I did

I wrote critical-path browser tests and gated merges on them. The work used Playwright, GitHub Actions, TypeScript and Jest. Every service is containerised so it runs the same on a laptop and in production.

## Results

- Release regressions down from about 5 to 1 per quarter.
- Suite runs in 7 minutes.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
