---
id: case-medical-imaging
type: case_study
project: medical-imaging
client_industry: healthcare research
date: 2021-04
skills: [PyTorch, computer vision, transfer learning]
synthetic: true
---

# Medical image classification prototype

**Client:** a healthcare research company (anonymised, synthetic)  
**Year:** 2021

## The problem

The client's a research team needed a baseline for chest X-ray triage.

## What I did

I fine-tuned an ImageNet backbone with heavy augmentation and site-wise validation. The work used PyTorch, computer vision and transfer learning. 

## Results

- AUC of 0.88 on a held-out hospital.
- Results written up for an internal review.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
