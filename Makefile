# GigBid. Windows without make: run the commands on the right directly.
PY ?= uv run python
.PHONY: install dev up test lint eval smoke-eval seed demo gen-client results tools-doc freeze-gigsim data

install:      ; uv sync --extra dev && cd apps/web && npm ci
dev:          ; $(PY) -m scripts.dev --reset --web
up:           ; cd infra && docker compose --env-file ../.env up --build
test:         ; $(PY) -m pytest -q
lint:         ; uv run ruff check . && cd apps/web && npm run typecheck
seed:         ; $(PY) -m scripts.seed
gen-client:   ; $(PY) -m scripts.export_openapi && cd apps/web && npm run gen:api
data:         ; $(PY) -m scripts.generate_personas && $(PY) -m scripts.build_gigsim_data
freeze-gigsim:; $(PY) -m scripts.gigsim_manifest --write
tools-doc:    ; $(PY) -m scripts.gen_tools_md

# Full evaluation: retrieval (all variants + ablation), decisions, GigSim outcomes (V0 vs shipped, A/B), then tables
eval:
	$(PY) -m evals.runners.rag_eval --set all --n 30 --out rag_variants
	$(PY) -m evals.runners.decision_eval --n 40 --out decisions_test
	$(PY) -m evals.runners.gigsim_outcomes --n 20 --variant v0_naive --out outcomes_v0_naive
	$(PY) -m evals.runners.gigsim_outcomes --n 20 --variant v8_corrective --out outcomes_v8_corrective
	$(PY) -m evals.runners.gigsim_outcomes --n 20 --variant v8_corrective --strategy question_first --out outcomes_question_first
	$(PY) -m evals.runners.ab_test
	$(PY) -m scripts.render_results
# LLM-dependent studies (need MODEL_PROFILE=open with GROQ_API_KEY, or a local Ollama)
eval-llm:
	$(PY) -m evals.runners.injection_eval --n 20
	$(PY) -m evals.runners.tool_granularity --n 40
	$(PY) -m evals.runners.multiagent_compare --n 4
	$(PY) -m evals.runners.judge_calibration run
smoke-eval:
	$(PY) -m evals.runners.decision_eval --n 10 --out smoke_decisions
	$(PY) -m evals.runners.gigsim_outcomes --n 3 --out smoke_outcomes
	$(PY) -m evals.check_thresholds
results:      ; $(PY) -m scripts.render_results
demo:         ; $(PY) -m scripts.dev --reset --web
