---
id: case-demand-forecast
type: case_study
project: demand-forecast
client_industry: retail
date: 2022-10
skills: [Python, time series forecasting, LightGBM, pandas]
synthetic: true
---

# Demand forecasting for a grocery chain

**Client:** a retail company (anonymised, synthetic)  
**Year:** 2022

## The problem

The client's store managers over-ordered fresh produce and threw away margin.

## What I did

I trained a global gradient-boosting model with holiday and weather features and produced daily forecasts per store and SKU. The work used Python, time series forecasting, LightGBM and pandas. Everything runs as scheduled DAG-based pipelines that re-run on failure.

## Results

- MAPE improved from 24% to 13%.
- Fresh-produce waste fell 9% across 14 stores.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
