---
id: case-fraud-scoring
type: case_study
project: fraud-scoring
client_industry: fintech
date: 2023-02
skills: [Python, XGBoost, FastAPI, feature engineering]
synthetic: true
---

# Real-time transaction fraud scoring

**Client:** a fintech company (anonymised, synthetic)  
**Year:** 2023

## The problem

The client's rule-based fraud checks blocked good customers and missed new attack patterns.

## What I did

I engineered velocity and device features and served the model behind a low-latency API. The work used Python, XGBoost, FastAPI and feature engineering. Transactions arrive on an event stream that fans out to several consumers. An in-memory cache sits in front of the database for hot lookups.

## Results

- P99 scoring latency of 38 ms.
- Caught 22% more fraud at the same false-positive rate.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
