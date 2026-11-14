---
id: case-llm-agent-crm
type: case_study
project: llm-agent-crm
client_industry: B2B SaaS
date: 2025-12
skills: [LangGraph, LangChain, Python, OpenAI API, tool calling]
synthetic: true
---

# Sales-research agent built with LangGraph

**Client:** a B2B SaaS company (anonymised, synthetic)  
**Year:** 2025

## The problem

The client's account executives spent 25 minutes researching each prospect.

## What I did

I designed a multi-step agent that searches approved sources, drafts a brief and asks a human to approve CRM updates. The work used LangGraph, LangChain, Python, OpenAI API and tool calling. Agent memory and the audit history are kept in a relational store. Slow steps run on a background worker queue with automatic retries.

## Results

- Research brief ready in about 90 seconds instead of 25 minutes.
- No CRM write happens without approval.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
