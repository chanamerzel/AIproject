---
name: candidate-eval
description: Builds or changes the independent Deep Agent worker that screens job applications with RAG, MCP Studio tools, and Tavily. Use when editing agent/, mcp_studio/, or screening reports.
---

# Candidate evaluation agent

## Steps

1. Follow `docs/05-agent-spec.md`. Do not score inside a Flask view.
2. Pipeline order is fixed: start screening event → extract profile → Chroma RAG → requirement coverage → Tavily → complete screening event.
3. Tools in `mcp_studio/` must stay pure functions with JSON in/out so they remain valid MCP Studio exports.
4. If no LLM API key is present, use the deterministic fallback in `agent/deep_agent.py` so tests and demos still run.
5. Persist the full report JSON on `ApplicationScreeningCompleted`. Do not store scores only on the projection without the event.

## Output shape

`overall_score`, `skill_coverage`, `semantic_fit`, `recommendation`, `strengths`, `gaps`, `web_evidence`, `cv_excerpts`.
