---
name: style_extractor
version: 1
---
## system
Given a proposal draft and the user's edited version, describe the user's editing preferences as at most 3 short, general, reusable rules (e.g. "Never use the word 'passionate'", "Cut the first sentence if it is a greeting"). Ignore one-off factual corrections. Output JSON {{"rules": [str]}}.

## user
ORIGINAL:
{original}

EDITED:
{edited}
