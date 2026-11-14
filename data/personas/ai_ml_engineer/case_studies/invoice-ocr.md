---
id: case-invoice-ocr
type: case_study
project: invoice-ocr
client_industry: accounting
date: 2023-03
skills: [Python, OCR, PyTorch, computer vision]
synthetic: true
---

# Invoice field extraction pipeline

**Client:** a accounting company (anonymised, synthetic)  
**Year:** 2023

## The problem

The client's an accounts-payable team keyed 1,500 invoices a week by hand.

## What I did

I fine-tuned a layout-aware extraction model and wrapped it in a pipeline that routes low-confidence fields to a human. The work used Python, OCR, PyTorch and computer vision. Slow steps run on a background worker queue with automatic retries. Every service is containerised so it runs the same on a laptop and in production.

## Results

- Processing time fell from about 6 minutes to 40 seconds per invoice.
- Field-level F1 of 0.94 on unseen suppliers.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
