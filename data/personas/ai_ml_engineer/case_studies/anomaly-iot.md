---
id: case-anomaly-iot
type: case_study
project: anomaly-iot
client_industry: energy
date: 2022-02
skills: [Python, anomaly detection, time series, scikit-learn]
synthetic: true
---

# Sensor anomaly detection for pumping stations

**Client:** a energy company (anonymised, synthetic)  
**Year:** 2022

## The problem

The client's pump failures were only noticed after a station went offline.

## What I did

I combined seasonal decomposition with isolation forests on vibration and pressure signals. The work used Python, anomaly detection, time series and scikit-learn. Sensor readings are stored in a database built for time-stamped data.

## Results

- Flagged pump failures 36 hours earlier on average.
- Alert volume kept under 5 a day.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
