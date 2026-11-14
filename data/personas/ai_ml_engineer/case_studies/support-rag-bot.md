---
id: case-support-rag-bot
type: case_study
project: support-rag-bot
client_industry: B2B SaaS
date: 2024-06
skills: [Python, LangChain, RAG, OpenAI API, FastAPI]
synthetic: true
---

# Retrieval-augmented support assistant

**Client:** a B2B SaaS company (anonymised, synthetic)  
**Year:** 2024

## The problem

The client's support agents answered the same tier-1 questions from a 900-page knowledge base.

## What I did

I chunked the docs by heading, added hybrid retrieval and citation checking, and exposed it as an API used by the help widget. The work used Python, LangChain, RAG, OpenAI API and FastAPI. Embeddings live in a managed vector index for semantic lookup. An in-memory cache sits in front of the database for hot lookups.

## Results

- Deflected 31% of tier-1 tickets in the first two months.
- Answer groundedness of 0.92 on a 200-question evaluation set.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
