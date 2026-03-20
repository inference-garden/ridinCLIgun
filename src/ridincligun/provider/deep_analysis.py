"""Deep analysis for commands that download and execute remote code.

Layer 3 of the layered review system. When a command pipes a remote
script to a shell (curl|bash, wget|sh, etc.), this module:
1. Extracts the URL from the command
2. Fetches the script content (with safety limits)
3. Builds a prompt for AI analysis of the script

SECURITY:
- Only fetches HTTP/HTTPS URLs
- Size-limited (max 64KB) to prevent memory abuse
- Timeout-limited (5s) to prevent hanging
- Content is sent to the AI for analysis, never executed
- User sees exactly what is being fetched (URL shown in UI)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── URL extraction ─────────────────────────────────────────────────

# Patterns that indicate download-and-execute
_PIPE_TO_SHELL = re.compile(
    r"""(curl|wget)\s+[^|]*?(https?://\S+).*?\|\s*(bash|sh|zsh|dash)""",
    re.IGNORECASE,
)

_DOWNLOAD_AND_EXEC = re.compile(
    r"""(curl|wget)\s+.*?(-o|-O|--output)\s+(\S+)\s+[^&]*(https?://\S+)"""
    r""".*?[;&]+\s*(bash|sh|source)\s+\3""",
    re.IGNORECASE,
)

# Simpler fallback: any URL in a command that also has | bash/sh
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")
_SHELL_PIPE = re.compile(r"\|\s*(bash|sh|zsh|dash)\b")


@dataclass(frozen=True)
class DeepAnalysisTrigger:
    """Result of checking whether a command needs deep analysis."""

    should_analyze: bool
    url: str = ""
    reason: str = ""


def check_deep_analysis_trigger(command: str) -> DeepAnalysisTrigger:
    """Check if a command downloads and executes remote code.

    Returns a trigger with the URL to fetch if deep analysis is warranted.
    """
    if not command:
        return DeepAnalysisTrigger(should_analyze=False)

    # Pattern 1: curl/wget URL | bash
    match = _PIPE_TO_SHELL.search(command)
    if match:
        url = match.group(2)
        return DeepAnalysisTrigger(
            should_analyze=True,
            url=_clean_url(url),
            reason="Pipes remote script to shell for execution",
        )

    # Pattern 2: download then execute
    match = _DOWNLOAD_AND_EXEC.search(command)
    if match:
        url = match.group(4)
        return DeepAnalysisTrigger(
            should_analyze=True,
            url=_clean_url(url),
            reason="Downloads script then executes it",
        )

    # Fallback: URL + shell pipe in same command
    urls = _URL_PATTERN.findall(command)
    if urls and _SHELL_PIPE.search(command):
        return DeepAnalysisTrigger(
            should_analyze=True,
            url=_clean_url(urls[0]),
            reason="URL combined with pipe to shell",
        )

    return DeepAnalysisTrigger(should_analyze=False)


def _clean_url(url: str) -> str:
    """Remove trailing punctuation that's not part of the URL."""
    # Strip trailing quotes, semicolons, pipes
    return url.rstrip("\"';|&)")


# ── Script fetching ────────────────────────────────────────────────

_MAX_SCRIPT_SIZE = 65_536  # 64KB max
_FETCH_TIMEOUT = 5.0  # seconds


@dataclass(frozen=True)
class FetchResult:
    """Result of fetching a remote script."""

    success: bool
    content: str = ""
    error: str = ""
    url: str = ""
    size_bytes: int = 0
    truncated: bool = False


async def fetch_script(url: str) -> FetchResult:
    """Fetch a remote script with safety limits.

    - Only HTTP/HTTPS
    - Max 64KB
    - 5s timeout
    - Never executes content
    """
    import asyncio

    if not url.startswith(("http://", "https://")):
        return FetchResult(success=False, error="Only HTTP/HTTPS URLs supported", url=url)

    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ridinCLIgun/0.2 (script-safety-check)"},
        )

        def _do_fetch() -> tuple[bytes, str]:
            with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:  # nosec B310
                content_type = resp.headers.get("Content-Type", "")
                data = resp.read(_MAX_SCRIPT_SIZE + 1)
                return data, content_type

        data, content_type = await asyncio.to_thread(_do_fetch)

        # Check if content looks like text
        if "html" in content_type.lower() and "text/plain" not in content_type.lower():
            # HTML pages are unlikely to be shell scripts — still analyze but note it
            pass

        truncated = len(data) > _MAX_SCRIPT_SIZE
        if truncated:
            data = data[:_MAX_SCRIPT_SIZE]

        try:
            content = data.decode("utf-8", errors="replace")
        except Exception:
            return FetchResult(success=False, error="Could not decode content as text", url=url)

        return FetchResult(
            success=True,
            content=content,
            url=url,
            size_bytes=len(data),
            truncated=truncated,
        )

    except TimeoutError:
        return FetchResult(success=False, error=f"Fetch timed out after {_FETCH_TIMEOUT}s", url=url)
    except Exception as e:
        return FetchResult(success=False, error=str(e), url=url)


# ── Deep analysis prompt ───────────────────────────────────────────

DEEP_ANALYSIS_SYSTEM = """\
You are a script security analyzer in ridinCLIgun, a terminal safety tool.

A user is about to download and execute a remote script. You must analyze
the script content and report what it does in plain, factual language.

Rules:
- List every significant action the script takes (installs, modifies, deletes, downloads)
- Flag any network calls, privilege escalation (sudo), or persistence mechanisms
- Flag obfuscated code, encoded payloads, or suspicious patterns
- Rate overall risk: "safe", "caution", "warning", or "danger"
- Keep the summary short — it's shown in a narrow side panel
- Be factual, not dramatic

Response format:
RISK: <safe|caution|warning|danger>
SUMMARY: <one-line description of what the script does>
ACTIONS:
- <action 1>
- <action 2>
- ...
CONCERNS: <security concerns, or "None">
"""


def build_deep_analysis_prompt(url: str, script_content: str, truncated: bool = False) -> str:
    """Build the prompt for deep script analysis."""
    parts = [f"Analyze this script downloaded from: {url}\n"]
    if truncated:
        parts.append("(Script was truncated at 64KB — analysis may be incomplete)\n")
    parts.append(f"```\n{script_content}\n```")
    return "\n".join(parts)
