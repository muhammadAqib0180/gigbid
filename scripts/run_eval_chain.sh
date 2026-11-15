#!/usr/bin/env bash
# Sequential evaluation chain used for the committed results (CPU-only laptop). Logs in data/processed/logs/.
# LLM-dependent steps use MODEL_PROFILE=open_small (Ollama qwen3:1.7b) and small n; rerun with
# MODEL_PROFILE=open (+GROQ_API_KEY) and the defaults in the Makefile for full-size runs.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-.venv/Scripts/python}
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 HF_HUB_DISABLE_PROGRESS_BARS=1 OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://127.0.0.1:11435}
L=data/processed/logs
mkdir -p $L
step() { echo "=== $(date +%H:%M:%S) $*" | tee -a $L/chain.log; "$@" >> $L/chain.log 2>&1; echo "--- exit $?" >> $L/chain.log; }

step $PY -m evals.runners.decision_eval --n 40 --profile test --concurrency 2 --out decisions_test
step $PY -m evals.runners.gigsim_outcomes --n 20 --variant v8_corrective --strategy evidence_first --out outcomes_v8_corrective
step $PY -m evals.runners.gigsim_outcomes --n 20 --variant v0_naive --strategy evidence_first --out outcomes_v0_naive
step $PY -m evals.runners.gigsim_outcomes --n 20 --variant v8_corrective --strategy question_first --out outcomes_question_first
step $PY -m evals.runners.ab_test --a outcomes_v8_corrective --b outcomes_question_first
step $PY -m evals.runners.change_request --label before
step $PY -m evals.runners.judge_calibration export --source outcomes_v8_corrective
NODE_TIMEOUT_S=600 step $PY -m evals.runners.injection_eval --n 12 --profile open_small
NODE_TIMEOUT_S=600 step $PY -m evals.runners.tool_granularity --n 20 --profile open_small
NODE_TIMEOUT_S=600 step $PY -m scripts.demo_single_agent --profile open_small
NODE_TIMEOUT_S=600 step $PY -m evals.runners.multiagent_compare --n 1 --profile open_small --timeout 1500
step $PY -m evals.runners.model_speed --models qwen3:1.7b,qwen3:4b --calls 2
echo "=== $(date +%H:%M:%S) chain done" | tee -a $L/chain.log
