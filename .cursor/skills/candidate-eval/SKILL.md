---
name: candidate-eval
description: Builds or changes the independent Deep Agent worker that screens job applications with RAG, MCP Studio tools, and Tavily. Use when editing agent/, mcp_studio/, or screening reports.
---

# Candidate evaluation agent

## Steps

1. Follow `docs/05-agent-spec.md`. Do not score inside a Flask view; screening runs only in `agent.worker`.
2. Keep the Deep Agent shape: an orchestrator with no screening tools of its own, delegating through `task` to `cv-analyst` (MCP Studio tools + `rag_cv_against_job`) and `web-researcher` (`tavily_web_search`).
3. Every tool goes through `_make_tools(application, trace, caller)` so the trace records the result and which agent called it. Tools read the CV from the application, never from model arguments.
4. Scores come from tool output in `_finalize`, never from the model's JSON. A skipped mandatory tool is run there and listed in `tools_skipped_by_agent`.
5. No LLM means no screening: `model_chain()` raises `AgentNotConfigured` and the worker leaves applications queued. `FITSCREEN_AGENT_MODE=pipeline` exists for tests only.
6. Tools in `mcp_studio/` stay pure functions with JSON in/out so they remain valid MCP Studio exports. Call them only over MCP (`agent/mcp_client.py`).
7. Persist the full report on `ApplicationScreeningCompleted`. Failures emit `ApplicationScreeningFailed`; re-screens emit `ApplicationRescreenRequested`.
8. Test with a scripted `GenericFakeChatModel` that walks orchestrator → subagents (see `tests/test_deep_agent.py`).

## Output shape

`overall_score`, `skill_coverage`, `semantic_fit`, `web_score`, `recommendation`, `agent_recommendation`, `agent_report_valid`, `summary`, `strengths`, `gaps`, `web_evidence`, `cv_excerpts`, `profile`, `tools_used`, `tools_skipped_by_agent`, `delegation`, `runtime`.
