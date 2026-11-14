---
id: case-semantic-search
type: case_study
project: semantic-search
client_industry: education
date: 2024-04
skills: [sentence-transformers, FAISS, Python, FastAPI]
synthetic: true
---

# Semantic search for a research library

**Client:** a education company (anonymised, synthetic)  
**Year:** 2024

## The problem

The client's keyword search failed on synonyms and paraphrased questions.

## What I did

I embedded 300,000 abstracts, added a re-ranker and built an evaluation set with librarians. The work used sentence-transformers, FAISS, Python and FastAPI. Every service is containerised so it runs the same on a laptop and in production.

## Results

- NDCG@10 improved from 0.51 to 0.74.
- Median query time 120 ms.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
