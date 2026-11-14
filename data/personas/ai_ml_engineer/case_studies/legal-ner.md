---
id: case-legal-ner
type: case_study
project: legal-ner
client_industry: legal
date: 2024-07
skills: [NLP, spaCy, Hugging Face Transformers, Python]
synthetic: true
---

# Contract clause extraction

**Client:** a legal company (anonymised, synthetic)  
**Year:** 2024

## The problem

The client's lawyers spent hours locating indemnity and termination clauses.

## What I did

I built a clause classifier and entity extractor and a review screen that highlights each clause. The work used NLP, spaCy, Hugging Face Transformers and Python. The base model was adapted with small parameter-efficient adapters trained on the client's documents.

## Results

- Clause extraction F1 of 0.89.
- First-pass review time down 55%.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
