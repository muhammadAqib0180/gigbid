---
id: case-saas-billing
type: case_study
project: saas-billing
client_industry: B2B SaaS
date: 2024-11
skills: [Next.js, TypeScript, Stripe, PostgreSQL, Prisma]
synthetic: true
---

# Subscription billing portal

**Client:** a B2B SaaS company (anonymised, synthetic)  
**Year:** 2024

## The problem

The client's customers could not upgrade, downgrade or update cards without emailing support.

## What I did

I built a self-serve billing area with proration, invoices and dunning emails. The work used Next.js, TypeScript, Stripe, PostgreSQL and Prisma. The payment provider pushes signed event callbacks that drive state changes.

## Results

- Failed-payment recovery up 14%.
- Billing support tickets down by two thirds.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
