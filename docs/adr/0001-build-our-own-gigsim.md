# ADR 0001 - Build our own GigSim from Kaggle data + synthetic generators
**Status:** accepted. **Context:** the starter kit (v0.1) shipped without the instructor's GigSim, persona corpora or dev
set - only 2 sample jobs. The instructor allowed combining the listed Kaggle datasets with clearly-labelled synthetic data.
**Decision:** `gigsim/` is a FastAPI simulator seeded from the 60k Upwork jobs dataset (real titles, descriptions, skills,
client attributes, Connects) plus synthetic scams, injections, reposts and client hidden preferences; rule-based seeded
client decisions. Frozen with `gigsim/MANIFEST.sha256`; CI fails if it changes.
**Consequences:** reproducible, free grading runs; reply rates measure agreement with *our* client model (documented as a
limitation). If the instructor's GigSim appears, only `GIGSIM_BASE_URL` and the adapter's paths change.
