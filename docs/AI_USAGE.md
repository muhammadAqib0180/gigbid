# AI usage disclosure

**Tool:** Claude Code (Anthropic, model Claude Opus 5.5) used as a pair-programmer in this repository, plus the open
models GigBid itself calls at runtime (documented in `agent/config.yaml`). Every file was reviewed by the author, who is
accountable for every line and can explain and change it in the viva.

| Area | Files | How the assistant was used |
|---|---|---|
| Data | `scripts/persona_specs.py`, `scripts/generate_personas.py`, `scripts/build_gigsim_data.py` | drafted generators and the persona project specs; author chose datasets, label rules and seeds |
| Simulator | `gigsim/*` | drafted the REST API and client decision model from the author's spec |
| Agents | `agent/**` | drafted nodes, graphs, state reducers, prompts, memory rules |
| RAG | `rag/**` | drafted loaders, BM25, variant presets, claim verification |
| MCP | `mcp_servers/**` | drafted the three servers, adapters and tests |
| API / worker / web | `apps/**`, `worker/**` | drafted routers, runner, Next.js screens |
| Evals / docs | `evals/**`, `docs/**`, `README.md` | drafted runners and documentation; **all numbers come from runs in `evals/results/`** |

## Things the assistant got wrong that were caught
1. **The retry wrapper swallowed LangGraph's `GraphInterrupt`.** The first version of `agent/nodes/common.py::node`
   caught every exception, so the approval interrupt was treated as a failure and the job went to `dead_letter`.
   Caught in the first end-to-end run; fixed by re-raising `GraphBubbleUp`.
2. **Sentence splitting cut "Next.js" in half.** The requirement regex ended sentences at any `.`, producing the
   requirement "...experience in Supabase, Next". Fixed with a terminator that ignores dots glued to the next word.
3. **ISO timestamps were redacted as phone numbers** by the Compliance Guard ("free at :00; :00"). Fixed with a
   date/time exclusion in `agent/safety.py::_is_phone` + a unit test.
4. **Number matching in claim verification compared "80,000" with "80 000"** and softened a true claim. Fixed by
   normalising numbers on both sides.
5. **SQLite concurrency**: sharing one aiosqlite connection for the LangGraph store across concurrent runs raised
   "cannot start a transaction within a transaction"; the store needs `isolation_level=None`.
6. **A clean install of the published Portfolio MCP server pulled MCP SDK 2.x**, where `FastMCP` was renamed; the
   dependency is now pinned to `mcp>=1.12,<2`.
