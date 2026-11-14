---
id: case-recipe-graphql
type: case_study
project: recipe-graphql
client_industry: food
date: 2022-07
skills: [GraphQL, Node.js, Prisma, PostgreSQL]
synthetic: true
---

# GraphQL API for a recipe app

**Client:** a food company (anonymised, synthetic)  
**Year:** 2022

## The problem

The client's the mobile app made dozens of calls per screen.

## What I did

I designed a GraphQL schema with batched resolvers. The work used GraphQL, Node.js, Prisma and PostgreSQL. Lookups are batched and cached per request.

## Results

- Removed N+1 queries; p95 from 900 ms to 160 ms.
- App screens load in one round trip.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
