---
id: case-churn-predictor
type: case_study
project: churn-predictor
client_industry: telecom
date: 2023-04
skills: [Python, scikit-learn, XGBoost, pandas, model evaluation]
synthetic: true
---

# Customer churn prediction for a telecom operator

**Client:** a telecom company (anonymised, synthetic)  
**Year:** 2023

## The problem

The client's monthly churn was 3.1% and the retention team called customers at random.

## What I did

I built a gradient-boosted classifier on 14 months of usage and billing data, calibrated the probabilities and ranked accounts by risk. The work used Python, scikit-learn, XGBoost, pandas and model evaluation. Every training run is versioned in an experiment tracker with its metrics. Each prediction ships with per-customer reasons the retention team can read.

## Results

- Recall on churners rose from 0.41 to 0.68 at the same precision.
- The retention team now targets about 3,200 at-risk accounts a month.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
