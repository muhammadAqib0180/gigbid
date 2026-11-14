---
id: case-mlops-pipeline
type: case_study
project: mlops-pipeline
client_industry: insurance
date: 2024-12
skills: [MLflow, Docker, Python, CI/CD]
synthetic: true
---

# Automated model retraining pipeline

**Client:** a insurance company (anonymised, synthetic)  
**Year:** 2024

## The problem

The client's retraining a pricing model took two days of manual work.

## What I did

I automated data checks, training, evaluation gates and staged rollout. The work used MLflow, Docker, Python and CI/CD. The API scales out automatically as pods behind a load balancer. Everything runs as scheduled DAG-based pipelines that re-run on failure.

## Results

- Retraining went from two days of manual work to a 40-minute pipeline.
- Every model version is reproducible.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
