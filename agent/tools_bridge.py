"""Legacy module. Decision email is not Gmail MCP until OAuth MCP is wired.

Tavily must be called from agent.mcp_client.call_tavily_search (MCP), not from here.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def send_decision_email(to_email: str, subject: str, body: str) -> bool:
    if os.getenv("GMAIL_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        logger.info(
            "Gmail MCP is not connected (NFR-9 optional adapter). "
            "Decision is stored as an event. Would email %s: %s",
            to_email,
            subject,
        )
        return False
    logger.warning("GMAIL_ENABLED=true but Gmail MCP client is not implemented yet.")
    return False
