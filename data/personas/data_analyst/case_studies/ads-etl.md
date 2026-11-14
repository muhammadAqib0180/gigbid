---
id: case-ads-etl
type: case_study
project: ads-etl
client_industry: marketing agency
date: 2024-10
skills: [Airflow, Python, BigQuery, ETL]
synthetic: true
---

# ETL pipeline for advertising platforms

**Client:** a marketing agency company (anonymised, synthetic)  
**Year:** 2024

## The problem

The client's analysts downloaded CSVs from seven ad platforms.

## What I did

I built daily extract-and-load jobs with schema checks and alerting. The work used Airflow, Python, BigQuery and ETL. Every service is containerised so it runs the same on a laptop and in production.

## Results

- 7 ad sources unified daily.
- Reporting delay from 3 days to same-day.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
