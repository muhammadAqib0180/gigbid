---
id: case-llm-eval-harness
type: case_study
project: llm-eval-harness
client_industry: AI startup
date: 2025-02
skills: [Python, LLM evaluation, RAGAS, pytest]
synthetic: true
---

# LLM evaluation harness

**Client:** a AI startup company (anonymised, synthetic)  
**Year:** 2025

## The problem

The client's prompt changes shipped without anyone knowing whether quality dropped.

## What I did

I built golden datasets, an LLM judge calibrated against human labels, and regression thresholds. The work used Python, LLM evaluation, RAGAS and pytest. The evaluation runs automatically on every pull request.

## Results

- Caught 3 quality regressions before release.
- Judge-human agreement of kappa 0.71.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
