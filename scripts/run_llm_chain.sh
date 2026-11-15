#!/usr/bin/env bash
# LLM-dependent studies (MODEL_PROFILE=open_small = Ollama qwen3:1.7b on CPU). Logs: data/processed/logs/llm_chain.log
set -u
cd "$(dirname "$0")/.."
PY=${PY:-.venv/Scripts/python}
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 HF_HUB_DISABLE_PROGRESS_BARS=1 OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://127.0.0.1:11435} NODE_TIMEOUT_S=600
L=data/processed/logs
step() { echo "=== $(date +%H:%M:%S) $*" | tee -a $L/llm_chain.log; "$@" >> $L/llm_chain.log 2>&1; echo "--- exit $?" >> $L/llm_chain.log; }
step $PY -m evals.runners.injection_eval --n 12 --profile open_small
step $PY -m evals.runners.tool_granularity --n 20 --profile open_small
step $PY -m scripts.demo_single_agent --profile open_small
step $PY -m evals.runners.multiagent_compare --n 1 --profile open_small --timeout 1500
step $PY -m evals.runners.model_speed --models qwen3:1.7b,qwen3:4b --calls 2
echo "=== $(date +%H:%M:%S) llm chain done" | tee -a $L/llm_chain.log
