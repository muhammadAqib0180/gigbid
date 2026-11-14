One versioned Markdown prompt per node (front matter `name`, `version`; sections `## system` and `## user`).
Loaded only through `agent/prompting.py::load_prompt`. CI (`tests/unit/test_prompts_in_dir.py`) fails if a node
builds an inline prompt. Job posts and client messages are always passed wrapped in `<untrusted_...>` tags.
