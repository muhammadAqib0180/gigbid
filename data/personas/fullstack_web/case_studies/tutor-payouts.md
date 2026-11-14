---
id: case-tutor-payouts
type: case_study
project: tutor-payouts
client_industry: education
date: 2024-08
skills: [Stripe Connect, Node.js, React, PostgreSQL]
synthetic: true
---

# Payouts for a tutoring marketplace

**Client:** a education company (anonymised, synthetic)  
**Year:** 2024

## The problem

The client's tutors were paid manually by bank transfer each Friday.

## What I did

I built onboarding, split payments and automatic payouts with reconciliation. The work used Stripe Connect, Node.js, React and PostgreSQL. The payment provider pushes signed event callbacks that drive state changes. A retried payout can never be paid twice.

## Results

- $480k processed with zero double payouts.
- Payout day moved from weekly to daily.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
