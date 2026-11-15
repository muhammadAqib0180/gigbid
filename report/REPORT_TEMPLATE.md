# GigBid: R&D Report

**AI-4016, Assignment II.** GigBid is a multi-agent freelancer copilot built with LangGraph, three MCP servers, a
retrieval layer that grounds every claim in the freelancer's portfolio, and a Next.js interface. It finds and assesses
jobs and drafts proposals and replies, but nothing is sent without human approval. Every number in this report comes from
a file in `evals/results/`, and each file records the commit that produced it.

{{STATIC_1_2}}

{{SECTION_3}}

{{SECTION_4}}

{{SECTION_5}}

{{SECTION_6}}

{{SECTION_7}}

{{SECTION_8}}

{{STATIC_9}}

{{SECTION_10}}

## Appendix. Graphs rendered from code
`python -m scripts.render_graphs` builds both graphs and exports `graph.get_graph().draw_mermaid()` to `docs/images/`;
CI fails if the exported files no longer match the code.

**Bid graph** (one thread per job):  
![Bid graph](../docs/images/bid_graph.png)

**Conversation graph** (one thread per client conversation):  
![Conversation graph](../docs/images/conversation_graph.png)
