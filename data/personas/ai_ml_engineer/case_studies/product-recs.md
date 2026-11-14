---
id: case-product-recs
type: case_study
project: product-recs
client_industry: e-commerce
date: 2022-12
skills: [Python, recommendation systems, PyTorch, implicit feedback]
synthetic: true
---

# Product recommendations for an online store

**Client:** a e-commerce company (anonymised, synthetic)  
**Year:** 2022

## The problem

The client's the store showed the same best-sellers to every visitor.

## What I did

I trained a two-tower model on clicks and purchases and served candidates with a re-ranking step. The work used Python, recommendation systems, PyTorch and implicit feedback. An in-memory cache sits in front of the database for hot lookups. Changes went through a controlled split test before full rollout.

## Results

- Click-through on recommendations rose 18% over four weeks.
- Average order value up 4%.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
