---
id: case-django-crm
type: case_study
project: django-crm
client_industry: real estate
date: 2022-02
skills: [Django, PostgreSQL, Python, REST APIs]
synthetic: true
---

# Custom CRM with task automation

**Client:** a real estate company (anonymised, synthetic)  
**Year:** 2022

## The problem

The client's agents tracked leads in shared spreadsheets and missed follow-ups.

## What I did

I built lead pipelines, automatic reminders and email sequences. The work used Django, PostgreSQL, Python and REST APIs. Slow steps run on a background worker queue with automatic retries. An in-memory cache sits in front of the database for hot lookups.

## Results

- Agents saved about 6 hours a week each.
- Lead response time halved.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
