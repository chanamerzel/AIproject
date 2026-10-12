"""Call tools over MCP JSON-RPC (stdio), not Python import."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def call_studio_tool(name: str, arguments: dict) -> dict:
    return _stdio_call(
        command=sys.executable,
        args=["-m", "mcp_studio"],
        arguments_env={"PYTHONPATH": str(ROOT), **os.environ},
        tool_name=name,
        arguments=arguments,
        cwd=str(ROOT),
    )


def call_tavily_search(query: str, max_results: int = 3) -> dict:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        return {
            "ok": False,
            "error": "TAVILY_API_KEY missing — Tavily MCP was not started",
            "results": [],
        }
    installed = shutil.which("tavily-mcp")
    if installed:
        command, args = installed, []
    else:
        command, args = ("npx.cmd" if os.name == "nt" else "npx"), ["-y", "tavily-mcp@latest"]
    try:
        raw = _stdio_call(
            command=command,
            args=args,
            arguments_env={**os.environ, "TAVILY_API_KEY": key},
            tool_name=("tavily_search", "tavily-search"),
            arguments={"query": query, "max_results": max_results},
            cwd=str(ROOT),
        )
        return {"ok": True, "results": _as_results(raw), "raw": raw}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "results": []}


GMAIL_PACKAGE = "@gongrzhe/server-gmail-autoauth-mcp@1.1.11"


def gmail_paths() -> tuple[Path, Path]:
    """Same lookup as the Gmail MCP server: env override, else ~/.gmail-mcp/."""
    folder = Path.home() / ".gmail-mcp"
    oauth = os.getenv("GMAIL_OAUTH_PATH", "").strip() or folder / "gcp-oauth.keys.json"
    credentials = os.getenv("GMAIL_CREDENTIALS_PATH", "").strip() or folder / "credentials.json"
    return Path(oauth), Path(credentials)


def gmail_not_configured() -> str | None:
    """Why Gmail MCP cannot send, or None when the OAuth client and the login token both exist."""
    oauth, credentials = gmail_paths()
    if not oauth.is_file():
        return f"{oauth} missing (Google OAuth client JSON)"
    if not credentials.is_file():
        return f"{credentials} missing (run scripts/gmail_auth.ps1 once)"
    return None


_GMAIL_SENT = re.compile(r"Email sent successfully with ID:\s*(\S+)")


def call_gmail_send(to: str, subject: str, body: str, html_body: str | None = None) -> dict:
    installed = shutil.which("gmail-mcp")
    if installed:
        command, args = installed, []
    else:
        command, args = ("npx.cmd" if os.name == "nt" else "npx"), ["-y", GMAIL_PACKAGE]
    arguments = {"to": [to], "subject": subject, "body": body, "mimeType": "text/plain"}
    if html_body:
        arguments.update(htmlBody=html_body, mimeType="multipart/alternative")
    try:
        raw = _stdio_call(
            command=command,
            args=args,
            arguments_env=dict(os.environ),
            tool_name=("send_email",),
            arguments=arguments,
            cwd=str(ROOT),
            timeout=90,
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    text = raw.get("text", "") if isinstance(raw, dict) else str(raw)
    # The server reports Gmail API errors as ordinary text ("Error: ..."), not as isError.
    match = _GMAIL_SENT.search(text)
    if not match:
        return {"ok": False, "error": text or "empty reply from send_email"}
    return {"ok": True, "message_id": match.group(1)}


def _as_results(raw) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if "results" in raw:
            return raw["results"]
        if "text" in raw:
            return _parse_tavily_text(raw["text"])
        return [raw]
    return _parse_tavily_text(str(raw))


_TAVILY_FIELD = re.compile(r"^(Title|URL|Content|Raw Content|ID|Score):\s?(.*)$")


def _parse_tavily_text(text: str) -> list[dict]:
    """tavily-mcp returns 'Title: ...\\nURL: ...\\nContent: ...' blocks as plain text."""
    results, current, field = [], {}, None
    for line in text.splitlines():
        match = _TAVILY_FIELD.match(line)
        if match:
            key, value = match.group(1).lower().replace(" ", "_"), match.group(2).strip()
            if key == "title" and current:
                results.append(current)
                current = {}
            current[key] = value
            field = key
        elif field == "content" and line.strip():
            current["content"] = f"{current.get('content', '')} {line.strip()}".strip()
    if current:
        results.append(current)
    results = [r for r in results if r.get("url")]
    return results or [{"content": text.strip()[:2000]}]


def _stdio_call(command, args, arguments_env, tool_name, arguments, cwd, timeout=None) -> dict:
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _run():
        if timeout:
            with anyio.fail_after(timeout):
                return await _session()
        return await _session()

    async def _session():
        params = StdioServerParameters(
            command=command,
            args=args,
            env={k: str(v) for k, v in arguments_env.items() if v is not None},
            cwd=cwd,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                name = tool_name
                if isinstance(tool_name, tuple):
                    available = {t.name for t in (await session.list_tools()).tools}
                    name = next((n for n in tool_name if n in available), None)
                    if not name:
                        raise RuntimeError(f"MCP server exposes none of {tool_name}; has {sorted(available)}")
                result = await session.call_tool(name, arguments)
                if getattr(result, "isError", False):
                    raise RuntimeError(_parse_tool_result(result))
                return _parse_tool_result(result)

    return anyio.run(_run)


def _parse_tool_result(result) -> dict:
    chunks = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            chunks.append(text)
    blob = "\n".join(chunks).strip()
    if not blob:
        if getattr(result, "structuredContent", None):
            return result.structuredContent
        return {}
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return {"text": blob}
