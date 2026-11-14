---
id: case-sql-tuning
type: case_study
project: sql-tuning
client_industry: fintech
date: 2022-01
skills: [SQL, PostgreSQL, query optimisation]
synthetic: true
---

# Slow report query optimisation

**Client:** a fintech company (anonymised, synthetic)  
**Year:** 2022

## The problem

The client's a daily reconciliation report took 14 minutes and timed out.

## What I did

I rewrote the query plan, removed correlated subqueries and added summary tables. The work used SQL, PostgreSQL and query optimisation. The hottest tables got the right composite indexes.

## Results

- Report runtime from 14 minutes to 40 seconds.
- No more timeouts.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
