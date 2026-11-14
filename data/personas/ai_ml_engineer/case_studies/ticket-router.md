---
id: case-ticket-router
type: case_study
project: ticket-router
client_industry: B2B SaaS
date: 2023-10
skills: [Hugging Face Transformers, PyTorch, fine-tuning, Python]
synthetic: true
---

# Support ticket routing classifier

**Client:** a B2B SaaS company (anonymised, synthetic)  
**Year:** 2023

## The problem

The client's tickets bounced between teams before reaching the right one.

## What I did

I fine-tuned a compact transformer on 80,000 historical tickets and distilled it for cheap inference. The work used Hugging Face Transformers, PyTorch, fine-tuning and Python. The model is exported to a framework-neutral graph for fast inference.

## Results

- Routing accuracy of 91%.
- Inference cost down 70% after distillation.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
