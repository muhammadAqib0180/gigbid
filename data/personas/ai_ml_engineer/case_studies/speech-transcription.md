---
id: case-speech-transcription
type: case_study
project: speech-transcription
client_industry: healthcare
date: 2024-07
skills: [Whisper, Python, LLM summarisation, FastAPI]
synthetic: true
---

# Call transcription and summarisation

**Client:** a healthcare company (anonymised, synthetic)  
**Year:** 2024

## The problem

The client's clinic staff wrote call notes by hand after each patient call.

## What I did

I transcribed calls, removed identifiers and generated structured summaries for staff to approve. The work used Whisper, Python, LLM summarisation and FastAPI. Slow steps run on a background worker queue with automatic retries. Raw audio is kept in cloud object storage with lifecycle rules.

## Results

- Summaries for about 1,800 calls a day.
- Word error rate of 7.9% on accented speech.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
