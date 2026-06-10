# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Remote script fetch and analysis

"""Deep analysis for commands that download and execute remote code.

Layer 3 of the layered review system. When a command pipes a remote
script to a shell (curl|bash, wget|sh, etc.), this module:
1. Extracts the URL from the command
2. Fetches the script content (with safety limits)
3. Builds a prompt for AI analysis of the script

SECURITY (B-S09 hardened):
- HTTPS only — http:// and every other scheme are rejected before any network use
- SSRF guard — the resolved IP(s) must be public; loopback/private/link-local/
  reserved/multicast and the cloud-metadata endpoint (169.254.169.254, incl.
  IPv4-mapped IPv6 forms) are refused before the request is made
- Redirects are re-validated on every hop — no transparent follow to an internal
  target via an open redirect
- Size-limited (max 1MB, see _MAX_SCRIPT_SIZE) and timeout-limited (15s)
- Content is sent to the AI for analysis, never executed
- The secret-mode gate is checked BEFORE the fetch (see app._do_deep_analysis),
  so toggling secret mode cancels the outbound request, not just the later send
- DNS-rebinding (TOCTOU) closed: the connection is PINNED to the IP that was
  resolved and validated (_PinnedHTTPSHandler) — a rebinding DNS server cannot
  pass validation with a public address and then serve an internal one at
  connect time. TLS SNI + certificate verification still run against the
  hostname, so pinning cannot weaken cert checks.
- Environment proxies are deliberately ignored for this fetch (the SSRF guard
  is unsound through a proxy, which resolves the name itself). In proxied-only
  networks the fetch fails gracefully into the "fetch failed" advisory.
"""

from __future__ import annotations

import functools
import http.client
import ipaddress
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from ridincligun.provider.prompt import _LOCALE_NATIVE_DIRECTIVE, get_mode_supplement

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

_MAX_SCRIPT_SIZE = 1_048_576  # 1MB max fetch size
_FETCH_TIMEOUT = 15.0  # seconds (larger scripts need more time)

# ── Model context limits (input tokens) ──────────────────────────
# Conservative estimates leaving room for system prompt + response.
# Values are *usable input tokens* after reserving ~2K for prompt overhead
# and ~1K for response tokens.

# Matched LONGEST-PREFIX-first (see _get_context_limit), so a specific family
# like "gpt-4.1" wins over the generic "gpt-4". Get this wrong and e.g.
# "gpt-4.1-mini" falls through to the 8K "gpt-4" entry and scripts are wrongly
# flagged "too large" (the bug this ordering fixes).
_MODEL_CONTEXT_LIMITS: dict[str, int] = {
    # Anthropic
    "claude-opus-4": 195_000,
    "claude-sonnet-4": 195_000,
    "claude-haiku-4": 195_000,
    "claude-3-5-sonnet": 195_000,
    "claude-3-5-haiku": 195_000,
    "claude-3-opus": 195_000,
    "claude-3-sonnet": 195_000,
    "claude-3-haiku": 195_000,
    # OpenAI — gpt-4.1 and gpt-5.x are large-context (~1M); cap at the 1MB
    # fetch size in tokens so a max-size script still fits.
    "gpt-5": 250_000,
    "gpt-4.1": 250_000,
    "gpt-4o-mini": 124_000,
    "gpt-4o": 124_000,
    "gpt-4-turbo": 124_000,
    "gpt-4": 6_000,  # legacy GPT-4 8K — only matched by bare "gpt-4*" ids
    "o1": 195_000,
    "o3": 195_000,
    # Mistral (Small 4 / Medium 3.5 are ~128K-class)
    "mistral-large": 124_000,
    "mistral-small": 124_000,
    "mistral-medium": 124_000,
}

_DEFAULT_CONTEXT_LIMIT = 30_000  # Conservative fallback for unknown models
_CHARS_PER_TOKEN = 4  # Rough estimate for token counting


@dataclass(frozen=True)
class FetchResult:
    """Result of fetching a remote script."""

    success: bool
    content: str = ""
    error: str = ""
    url: str = ""
    size_bytes: int = 0
    truncated: bool = False


_USER_AGENT = "ridinCLIgun/0.4 (script-safety-check)"
_MAX_REDIRECTS = 5
_BLOCK_MSG = (
    "Refused: the URL resolves to a private, loopback, link-local, or reserved address (SSRF guard)"
)


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True if an IP must never be fetched (SSRF guard).

    Rejects loopback, private, link-local (incl. the 169.254.169.254 cloud
    metadata endpoint), reserved, multicast, unspecified, and any non-global
    address. IPv4-mapped IPv6 (``::ffff:a.b.c.d``) is unwrapped first so a blocked
    v4 address can't be smuggled through in v6 form.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or not ip.is_global
    )


def _resolve_validated(host: str, port: int) -> tuple[str | None, str | None]:
    """Resolve *host* once, validate every address, and return one to pin.

    Returns ``(ip, None)`` if safe — *ip* is the first resolved address, used
    as the pinned connect target — or ``(None, error)`` if unsafe. An IP
    literal is validated directly (no DNS). For a hostname, **every** resolved
    address must be public — if any is blocked the whole host is refused (fail
    closed; a multi-record DNS answer can't smuggle one internal address past
    the check).
    """
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _ip_is_blocked(literal):
            return None, _BLOCK_MSG
        return host, None

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError:
        return None, "Could not resolve host"
    if not infos:
        return None, "Could not resolve host"
    ips: list[str] = []
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return None, _BLOCK_MSG
        if _ip_is_blocked(ip):
            return None, _BLOCK_MSG
        ips.append(str(ip))
    return ips[0], None


def _resolve_and_check(host: str, port: int) -> str | None:
    """Boolean form of :func:`_resolve_validated` (pre-flight URL checks)."""
    _ip, err = _resolve_validated(host, port)
    return err


def _check_url(url: str) -> str | None:
    """Validate a URL for fetching: HTTPS-only + SSRF guard on the host.

    Returns ``None`` if safe, else an error string.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        return "Only HTTPS URLs are allowed"
    host = parts.hostname
    if not host:
        return "Invalid URL (no host)"
    try:
        port = parts.port or 443
    except ValueError:
        return "Invalid URL (bad port)"
    return _resolve_and_check(host, port)


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect hop before following it.

    urllib would otherwise transparently follow a 3xx to an arbitrary host —
    including an internal/metadata target reached via an open redirect. Each hop's
    target is re-checked (HTTPS + SSRF); an unsafe target raises instead of being
    followed.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        err = _check_url(newurl)
        if err:
            raise urllib.error.URLError(f"blocked redirect to {newurl!r}: {err}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection whose TCP target is a pre-validated, pinned IP.

    DNS-rebinding defense: the socket connects to *pinned_ip* (no second DNS
    lookup), while TLS SNI and certificate verification still use the real
    hostname — so the cert must be valid for the host the user's command named.
    """

    def __init__(self, host: str, *, pinned_ip: str, **kwargs) -> None:
        super().__init__(host, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:  # pragma: no cover - exercised via handler tests
        sock = socket.create_connection(
            (self._pinned_ip, self.port), self.timeout, self.source_address
        )
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    """Resolve + validate + pin in ONE step at connect time.

    This is the authoritative SSRF check: it runs for the initial request and
    for every redirect hop (each hop re-enters ``https_open``), and the address
    that passed validation is exactly the address the socket connects to —
    closing the resolve/connect TOCTOU window a rebinding DNS server exploits.
    """

    def https_open(self, req):  # type: ignore[override]
        parts = urlsplit(req.full_url)
        host = parts.hostname
        if not host:
            raise urllib.error.URLError("Invalid URL (no host)")
        try:
            port = parts.port or 443
        except ValueError:
            raise urllib.error.URLError("Invalid URL (bad port)") from None
        pinned_ip, err = _resolve_validated(host, port)
        if err or pinned_ip is None:
            raise urllib.error.URLError(err or _BLOCK_MSG)
        factory = functools.partial(_PinnedHTTPSConnection, pinned_ip=pinned_ip)
        return self.do_open(factory, req, context=self._context)


def _http_get(req: urllib.request.Request, timeout: float):
    """Perform an HTTP GET with redirect hops re-validated by the SSRF guard.

    A separate module-level seam so tests can stub the network without patching
    urllib internals.
    """
    # ProxyHandler({}) disables environment proxies: through a proxy the SSRF
    # guard and IP pinning would be meaningless (the proxy resolves the name).
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _GuardedRedirectHandler,
        _PinnedHTTPSHandler(),
    )
    # Scheme is validated HTTPS-only before we get here; the handler above
    # re-validates and pins the address for the initial request and every hop.
    return opener.open(req, timeout=timeout)


async def fetch_script(url: str) -> FetchResult:
    """Fetch a remote script with B-S09 safety guards.

    HTTPS-only, SSRF guard on the resolved IP(s), redirects re-validated per hop,
    1MB / 15s caps. Content is returned for AI analysis and never executed. See
    the module docstring for the full security model and the DNS-rebinding caveat.
    """
    import asyncio

    # Validate the initial URL before any network activity (scheme + SSRF).
    err = _check_url(url)
    if err:
        return FetchResult(success=False, error=err, url=url)

    def _do_fetch() -> FetchResult:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with _http_get(req, _FETCH_TIMEOUT) as resp:
                data = resp.read(_MAX_SCRIPT_SIZE + 1)
                final_url = resp.geturl()
        except urllib.error.HTTPError as e:
            return FetchResult(success=False, error=f"HTTP error {e.code}", url=url)
        except (urllib.error.URLError, TimeoutError) as e:
            reason = getattr(e, "reason", e)
            return FetchResult(success=False, error=str(reason), url=url)
        except Exception as e:  # noqa: BLE001 — never let a fetch error crash the review
            return FetchResult(success=False, error=str(e), url=url)

        truncated = len(data) > _MAX_SCRIPT_SIZE
        if truncated:
            data = data[:_MAX_SCRIPT_SIZE]
        content = data.decode("utf-8", errors="replace")
        return FetchResult(
            success=True,
            content=content,
            url=final_url or url,
            size_bytes=len(data),
            truncated=truncated,
        )

    return await asyncio.to_thread(_do_fetch)


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
EXPLANATION: <the script's significant actions — installs, modifies, deletes,
downloads, network calls, privilege escalation, persistence — and any security
concerns, as short factual lines>
SUGGESTION: <how to proceed safely, or "None">
"""
# NOTE: the response format above MUST stay parseable by the shared adapter
# parser (RISK/SUMMARY/EXPLANATION/SUGGESTION — see provider/*. _parse_response).
# An earlier ACTIONS/CONCERNS format was silently dropped by that parser;
# tests/test_deep_analysis.py pins the compatibility.


def build_deep_analysis_system_prompt(locale: str = "en", mode: str = "default") -> str:
    """Compose the dedicated Layer 3 system prompt.

    Mirrors ``build_system_prompt()`` composition — base + mode tone + language
    instruction placed LAST (recency helps weaker models honour it, B-014) —
    but on the deep-analysis base prompt and with this format's field names.
    """
    parts = [DEEP_ANALYSIS_SYSTEM.rstrip()]

    mode_supplement = get_mode_supplement(mode)
    if mode_supplement:
        parts.append(f"\nTone and audience:\n{mode_supplement}")

    if locale and locale != "en":
        lang_name = _LANGUAGE_NAMES.get(locale, locale)
        lang_line = (
            f"\nIMPORTANT: Write all SUMMARY, EXPLANATION, and SUGGESTION content "
            f"in {lang_name}. Keep the response format headers "
            f"(RISK, SUMMARY, EXPLANATION, SUGGESTION) in English."
        )
        native = _LOCALE_NATIVE_DIRECTIVE.get(locale, "")
        if native:
            lang_line += f"\n{native}"
        parts.append(lang_line)

    return "\n".join(parts)


def _get_context_limit(model_name: str) -> int:
    """Look up the usable context-window size for a model.

    Matches by prefix so versioned ids (``claude-sonnet-4-6``, ``gpt-5.4-mini``)
    resolve to their family limit. Prefixes are tried **longest-first** so a
    specific family (``gpt-4.1``) wins over a generic one (``gpt-4``) — otherwise
    ``gpt-4.1-mini`` would collide with the 8K ``gpt-4`` entry.
    """
    if not model_name:
        return _DEFAULT_CONTEXT_LIMIT
    lower = model_name.lower()
    for prefix, limit in sorted(_MODEL_CONTEXT_LIMITS.items(), key=lambda kv: -len(kv[0])):
        if lower.startswith(prefix):
            return limit
    return _DEFAULT_CONTEXT_LIMIT


def fit_script_to_context(
    script_content: str,
    model_name: str = "",
) -> tuple[str, bool]:
    """Trim script content to fit the model's context window if necessary.

    Returns ``(content, was_truncated)``.
    In practice, scripts under ~500KB fit all major models.
    """
    limit_tokens = _get_context_limit(model_name)
    # Reserve tokens for the system prompt (~800) + user prompt framing (~200)
    # + desired response (~1000)
    available_tokens = limit_tokens - 2_000
    max_chars = available_tokens * _CHARS_PER_TOKEN

    if len(script_content) <= max_chars:
        return script_content, False

    return script_content[:max_chars], True


_LANGUAGE_NAMES: dict[str, str] = {
    "de": "German",
    "fr": "French",
    "en": "English",
}


def build_deep_analysis_prompt(
    url: str,
    script_content: str,
    truncated: bool = False,
    locale: str = "en",
) -> str:
    """Build the prompt for deep script analysis."""
    parts = [f"Analyze this script downloaded from: {url}\n"]
    if truncated:
        parts.append(
            "IMPORTANT: This script was truncated to fit the analysis window. "
            "You are seeing only the first part. Your analysis is INCOMPLETE. "
            "State this clearly in your SUMMARY (e.g. 'Partial analysis — "
            "script truncated'). Flag in CONCERNS that unreviewed code may "
            "contain additional actions.\n"
        )
    if locale and locale != "en":
        lang_name = _LANGUAGE_NAMES.get(locale, locale)
        parts.append(
            f"IMPORTANT: Write all SUMMARY, EXPLANATION, and SUGGESTION content "
            f"in {lang_name}. Keep the response format headers "
            f"(RISK, SUMMARY, EXPLANATION, SUGGESTION) in English.\n"
        )
    parts.append(f"```\n{script_content}\n```")
    return "\n".join(parts)
