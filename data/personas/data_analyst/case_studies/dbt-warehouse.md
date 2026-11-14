---
id: case-dbt-warehouse
type: case_study
project: dbt-warehouse
client_industry: B2B SaaS
date: 2024-04
skills: [dbt, Snowflake, SQL, Fivetran]
synthetic: true
---

# Modern data stack migration

**Client:** a B2B SaaS company (anonymised, synthetic)  
**Year:** 2024

## The problem

The client's finance and product disagreed on revenue numbers.

## What I did

I loaded sources into Snowflake and rebuilt the metrics layer as tested SQL models. The work used dbt, Snowflake, SQL and Fivetran. Automated checks catch nulls, duplicates and unexpected values before reports refresh.

## Results

- 37 dbt models with tests.
- Finance numbers reconciled to within 0.2%.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
