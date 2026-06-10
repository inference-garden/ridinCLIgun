# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for deep script analysis

"""Tests for the deep analysis module (URL extraction, trigger detection, fetch)."""

import ipaddress
import socket
import urllib.error

import pytest

import ridincligun.provider.deep_analysis as da
from ridincligun.provider.deep_analysis import (
    _FETCH_TIMEOUT,
    _MAX_SCRIPT_SIZE,
    DEEP_ANALYSIS_SYSTEM,
    FetchResult,
    _check_url,
    _get_context_limit,
    _GuardedRedirectHandler,
    _ip_is_blocked,
    build_deep_analysis_prompt,
    build_deep_analysis_system_prompt,
    check_deep_analysis_trigger,
    fetch_script,
    fit_script_to_context,
)

# ── Trigger detection ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "command",
    [
        "curl https://example.com/install.sh | bash",
        "curl -fsSL https://example.com/setup | sh",
        "wget https://example.com/script.sh | bash",
        "curl -o- https://example.com/nvm.sh | zsh",
        "wget -qO- https://raw.githubusercontent.com/org/repo/main/install.sh | bash",
    ],
)
def test_pipe_to_shell_triggers(command: str) -> None:
    trigger = check_deep_analysis_trigger(command)
    assert trigger.should_analyze
    assert trigger.url.startswith("http")
    assert trigger.reason


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "git status",
        "curl https://example.com",
        "wget https://example.com/file.tar.gz",
        "echo hello | grep h",
        "cat file.txt | bash_completion",  # bash_completion is not bash
        "pip install requests",
    ],
)
def test_safe_commands_no_trigger(command: str) -> None:
    trigger = check_deep_analysis_trigger(command)
    assert not trigger.should_analyze


def test_empty_command_no_trigger() -> None:
    trigger = check_deep_analysis_trigger("")
    assert not trigger.should_analyze


def test_trigger_extracts_url() -> None:
    trigger = check_deep_analysis_trigger("curl https://example.com/install.sh | bash")
    assert trigger.url == "https://example.com/install.sh"


def test_trigger_cleans_url_trailing_pipe() -> None:
    """URL should not include trailing pipe or quotes."""
    trigger = check_deep_analysis_trigger("curl 'https://example.com/s.sh' | bash")
    assert trigger.should_analyze
    assert "|" not in trigger.url
    assert "'" not in trigger.url


def test_trigger_reason_not_empty() -> None:
    trigger = check_deep_analysis_trigger("curl https://x.com/s | sh")
    assert trigger.reason


# ── Prompt building ────────────────────────────────────────────────


def test_deep_analysis_prompt_contains_url() -> None:
    prompt = build_deep_analysis_prompt(
        "https://example.com/install.sh",
        "#!/bin/bash\necho hello",
    )
    assert "https://example.com/install.sh" in prompt
    assert "echo hello" in prompt


def test_deep_analysis_prompt_truncation_note() -> None:
    prompt = build_deep_analysis_prompt(
        "https://example.com/install.sh",
        "#!/bin/bash\necho hello",
        truncated=True,
    )
    assert "truncated" in prompt.lower()


def test_deep_analysis_system_prompt_format_matches_shared_parser() -> None:
    """The deep prompt's response format MUST be what the adapters parse.

    Regression pin: an earlier ACTIONS/CONCERNS format was silently dropped by
    the shared RISK/SUMMARY/EXPLANATION/SUGGESTION parser (_parse_response) —
    deep analysis would render only the one-line summary.
    """
    for field in ("RISK:", "SUMMARY:", "EXPLANATION:", "SUGGESTION:"):
        assert field in DEEP_ANALYSIS_SYSTEM, field
    for stale in ("ACTIONS:", "CONCERNS:"):
        assert stale not in DEEP_ANALYSIS_SYSTEM, stale


# ── Dedicated Layer 3 system prompt composition ────────────────────


def test_deep_system_prompt_default_is_base_only() -> None:
    """English + default mode: exactly the dedicated base, no supplements."""
    prompt = build_deep_analysis_system_prompt()
    assert prompt == DEEP_ANALYSIS_SYSTEM.rstrip()


def test_deep_system_prompt_locale_de() -> None:
    """DE: language instruction with the DEEP field names + native directive (B-014)."""
    prompt = build_deep_analysis_system_prompt(locale="de")
    assert prompt.startswith("You are a script security analyzer")
    assert "in German" in prompt
    assert "Deutsch" in prompt  # native-language reinforcement
    # Same field names the shared parser extracts
    assert "SUMMARY, EXPLANATION, and SUGGESTION" in prompt


def test_deep_system_prompt_locale_fr() -> None:
    prompt = build_deep_analysis_system_prompt(locale="fr")
    assert "in French" in prompt
    assert "français" in prompt


def test_deep_system_prompt_language_instruction_is_last() -> None:
    """Recency: the language block must come AFTER the analyzer instructions."""
    prompt = build_deep_analysis_system_prompt(locale="de", mode="explorer")
    assert prompt.rindex("Deutsch") > prompt.index("SUGGESTION:")


def test_deep_system_prompt_explorer_mode_supplement() -> None:
    """Explorer mode keeps its tone in deep analysis (parity with Layer 2)."""
    prompt = build_deep_analysis_system_prompt(mode="explorer")
    assert "Tone and audience:" in prompt
    assert prompt.startswith("You are a script security analyzer")


# ── FetchResult safety states ────────────────────────────────────


def test_fetch_result_truncated_state() -> None:
    """FetchResult correctly represents truncation."""
    result = FetchResult(
        success=True,
        content="x" * 65536,
        url="https://example.com/big.sh",
        size_bytes=65536,
        truncated=True,
    )
    assert result.success
    assert result.truncated
    assert result.size_bytes == 65536


def test_fetch_result_failure_state() -> None:
    """FetchResult correctly represents fetch failure."""
    result = FetchResult(
        success=False,
        error="Fetch timed out after 5.0s",
        url="https://example.com/slow.sh",
    )
    assert not result.success
    assert "timed out" in result.error


def test_fetch_result_network_error_state() -> None:
    """FetchResult correctly represents network error."""
    result = FetchResult(
        success=False,
        error="Connection refused",
        url="https://example.com/down.sh",
    )
    assert not result.success
    assert result.error == "Connection refused"


# ── Model-aware context fitting ─────────────────────────────────


def test_context_limit_known_model() -> None:
    """Known model IDs resolve to their family limit."""
    limit = _get_context_limit("claude-sonnet-4-20250514")
    assert limit == 195_000


def test_context_limit_unknown_model_uses_default() -> None:
    """Unknown model falls back to conservative default."""
    limit = _get_context_limit("some-unknown-model-v99")
    assert limit == 30_000


def test_context_limit_gpt41_does_not_collide_with_gpt4() -> None:
    """Regression (#2b): `gpt-4.1-mini` must NOT match the 8K `gpt-4` entry.

    Longest-prefix matching means the specific `gpt-4.1` family wins. The bug made
    a 108 KB script wrongly "too large" because gpt-4.1-mini resolved to 6K tokens.
    """
    assert _get_context_limit("gpt-4.1-mini") == 250_000
    assert _get_context_limit("gpt-5.4-mini") == 250_000
    assert _get_context_limit("gpt-5.4") == 250_000
    assert _get_context_limit("gpt-4o-mini") == 124_000
    assert _get_context_limit("gpt-4") == 6_000  # bare legacy GPT-4 still 8K-class


def test_context_limit_gpt41_fits_a_large_script() -> None:
    """The collision previously truncated a ~108 KB script on gpt-4.1-mini."""
    script = "x" * 108_144
    _content, truncated = fit_script_to_context(script, "gpt-4.1-mini")
    assert not truncated


def test_context_limit_empty_model_uses_default() -> None:
    limit = _get_context_limit("")
    assert limit == 30_000


def test_fit_script_small_script_unchanged() -> None:
    """Small scripts pass through without truncation."""
    script = "#!/bin/bash\necho hello"
    content, truncated = fit_script_to_context(script, "claude-sonnet-4-20250514")
    assert content == script
    assert not truncated


def test_fit_script_huge_script_truncated() -> None:
    """Scripts exceeding model context are truncated."""
    # Create a script larger than any model's context window
    # Default limit: 30_000 tokens - 2000 overhead = 28_000 * 4 chars = 112_000 chars
    huge_script = "x" * 200_000
    content, truncated = fit_script_to_context(huge_script, "")
    assert truncated
    assert len(content) < len(huge_script)


def test_fit_script_model_aware_limit() -> None:
    """Claude's larger context allows bigger scripts than default."""
    # 150K chars fits in Claude (195K - 2K = 193K tokens * 4 = 772K chars)
    # but would exceed small Mistral (30K - 2K = 28K tokens * 4 = 112K chars)
    script = "x" * 150_000
    content_claude, trunc_claude = fit_script_to_context(script, "claude-sonnet-4-20250514")
    content_default, trunc_default = fit_script_to_context(script, "")
    assert not trunc_claude  # Fits in Claude
    assert trunc_default  # Doesn't fit in default/small model


# ── fetch_script security boundary — B-S09 (networkless) ──────────


class _FakeResp:
    """Minimal stand-in for the urlopen context manager."""

    def __init__(self, data: bytes, url: str = "https://example.com/x") -> None:
        self._data = data
        self._url = url
        self.headers = {"Content-Type": "text/plain"}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n: int) -> bytes:
        return self._data[:n]

    def geturl(self) -> str:
        return self._url


def _patch_resolver(monkeypatch, ip: str) -> None:
    """Make every DNS lookup resolve to a single fixed IP."""

    def _fake(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake)


def _ban_network(monkeypatch) -> None:
    """Fail loudly if anything tries to resolve or open a connection."""

    def _no_dns(*args, **kwargs):
        raise AssertionError("network must not be touched")

    monkeypatch.setattr(socket, "getaddrinfo", _no_dns)
    monkeypatch.setattr(da, "_http_get", _no_dns)


# ── SSRF guard: IP classification ─────────────────────────────────


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # private
        "172.16.5.4",  # private
        "192.168.1.1",  # private
        "169.254.169.254",  # AWS/GCP cloud metadata
        "0.0.0.0",  # unspecified
        "::1",  # IPv6 loopback
        "fe80::1",  # IPv6 link-local
        "fc00::1",  # IPv6 unique-local
        "::ffff:169.254.169.254",  # IPv4-mapped IPv6 metadata
        "::ffff:127.0.0.1",  # IPv4-mapped IPv6 loopback
    ],
)
def test_ip_is_blocked_rejects_internal(ip) -> None:
    assert _ip_is_blocked(ipaddress.ip_address(ip)) is True


@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "2606:2800:220:1::1"])
def test_ip_is_blocked_allows_public(ip) -> None:
    assert _ip_is_blocked(ipaddress.ip_address(ip)) is False


# ── _check_url: scheme + SSRF ─────────────────────────────────────


def test_check_url_rejects_http() -> None:
    assert _check_url("http://example.com/install.sh") == "Only HTTPS URLs are allowed"


@pytest.mark.parametrize("url", ["ftp://h/x", "file:///etc/passwd", "data:,hi", "//h/x"])
def test_check_url_rejects_non_https_schemes(url) -> None:
    assert _check_url(url) == "Only HTTPS URLs are allowed"


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/x",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/x",
        "https://192.168.0.1/x",
    ],
)
def test_check_url_blocks_internal_ip_literals(url) -> None:
    # IP literals are validated directly — no DNS needed.
    assert _check_url(url) == da._BLOCK_MSG


def test_check_url_blocks_hostname_resolving_internal(monkeypatch) -> None:
    _patch_resolver(monkeypatch, "10.0.0.5")
    assert _check_url("https://intranet.example/x") == da._BLOCK_MSG


def test_check_url_allows_public_host(monkeypatch) -> None:
    _patch_resolver(monkeypatch, "93.184.216.34")
    assert _check_url("https://example.com/install.sh") is None


# ── Redirect revalidation ─────────────────────────────────────────


def test_guarded_redirect_blocks_internal_target() -> None:
    """A redirect to an internal/metadata host must raise, not be followed."""
    handler = _GuardedRedirectHandler()
    with pytest.raises(urllib.error.URLError):
        handler.redirect_request(None, None, 302, "Found", {}, "https://169.254.169.254/latest/")


def test_guarded_redirect_blocks_http_downgrade() -> None:
    handler = _GuardedRedirectHandler()
    with pytest.raises(urllib.error.URLError):
        handler.redirect_request(None, None, 302, "Found", {}, "http://example.com/x")


# ── fetch_script integration (networkless) ────────────────────────


@pytest.mark.asyncio
async def test_fetch_script_rejects_http(monkeypatch):
    """http:// is rejected up front — no DNS, no connection."""
    _ban_network(monkeypatch)
    result = await fetch_script("http://example.com/install.sh")
    assert not result.success
    assert "HTTPS" in result.error


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["https://127.0.0.1/x", "https://169.254.169.254/x"])
async def test_fetch_script_blocks_internal_ip_literal(url, monkeypatch):
    """An internal IP literal is refused before any network activity."""
    _ban_network(monkeypatch)
    result = await fetch_script(url)
    assert not result.success
    assert result.error == da._BLOCK_MSG


@pytest.mark.asyncio
async def test_fetch_script_blocks_hostname_resolving_internal(monkeypatch):
    """A public-looking hostname that resolves to a private IP is refused."""
    _patch_resolver(monkeypatch, "10.0.0.5")
    monkeypatch.setattr(da, "_http_get", lambda *a, **k: pytest.fail("must not fetch"))
    result = await fetch_script("https://intranet.example/x")
    assert not result.success
    assert result.error == da._BLOCK_MSG


@pytest.mark.asyncio
async def test_fetch_script_blocked_redirect_surfaces_error(monkeypatch):
    """A blocked-redirect URLError from the opener becomes a clean fetch failure."""
    _patch_resolver(monkeypatch, "93.184.216.34")

    def _raise(req, timeout):
        raise urllib.error.URLError("blocked redirect to 'https://127.0.0.1/x': refused")

    monkeypatch.setattr(da, "_http_get", _raise)
    result = await fetch_script("https://example.com/install.sh")
    assert not result.success
    assert "blocked redirect" in result.error


@pytest.mark.asyncio
async def test_fetch_script_uses_timeout_and_returns_content(monkeypatch):
    """A valid https fetch (public IP) passes the timeout and returns decoded content."""
    _patch_resolver(monkeypatch, "93.184.216.34")
    captured: dict[str, object] = {}

    def fake_get(req, timeout):
        captured["timeout"] = timeout
        captured["url"] = req.full_url
        return _FakeResp(b"echo hello", url="https://example.com/install.sh")

    monkeypatch.setattr(da, "_http_get", fake_get)

    result = await fetch_script("https://example.com/install.sh")

    assert result.success
    assert result.content == "echo hello"
    assert not result.truncated
    assert captured["timeout"] == _FETCH_TIMEOUT
    assert captured["url"] == "https://example.com/install.sh"


@pytest.mark.asyncio
async def test_fetch_script_enforces_size_cap(monkeypatch):
    """Oversized responses are truncated to the cap, not pulled in unbounded."""
    _patch_resolver(monkeypatch, "93.184.216.34")
    big = b"a" * (_MAX_SCRIPT_SIZE + 500)
    monkeypatch.setattr(da, "_http_get", lambda req, timeout: _FakeResp(big))

    result = await fetch_script("https://example.com/big.sh")

    assert result.success
    assert result.truncated
    assert result.size_bytes == _MAX_SCRIPT_SIZE
    assert len(result.content) <= _MAX_SCRIPT_SIZE


# ── DNS-rebinding defense: pinned connect ─────────────────────────


def test_resolve_validated_returns_first_public_ip(monkeypatch) -> None:
    _patch_resolver(monkeypatch, "93.184.216.34")
    ip, err = da._resolve_validated("example.com", 443)
    assert err is None
    assert ip == "93.184.216.34"


def test_resolve_validated_ip_literal_passthrough() -> None:
    ip, err = da._resolve_validated("93.184.216.34", 443)
    assert err is None
    assert ip == "93.184.216.34"


def test_resolve_validated_blocked_returns_error(monkeypatch) -> None:
    _patch_resolver(monkeypatch, "10.0.0.5")
    ip, err = da._resolve_validated("example.com", 443)
    assert ip is None
    assert err


def test_pinned_connection_uses_validated_ip_and_hostname_sni(monkeypatch) -> None:
    """TCP goes to the pinned IP; TLS SNI/cert checks use the real hostname."""
    from unittest.mock import MagicMock

    connected: list[tuple] = []

    def _fake_create_connection(addr, timeout=None, source_address=None):
        connected.append(addr)
        return MagicMock()

    class _FakeCtx:
        def __init__(self) -> None:
            self.hostnames: list[str | None] = []

        def wrap_socket(self, sock, server_hostname=None):
            self.hostnames.append(server_hostname)
            return sock

    monkeypatch.setattr(socket, "create_connection", _fake_create_connection)
    ctx = _FakeCtx()
    conn = da._PinnedHTTPSConnection("example.com", pinned_ip="93.184.216.34", context=ctx)
    conn.connect()

    assert connected == [("93.184.216.34", 443)]  # no DNS at connect time
    assert ctx.hostnames == ["example.com"]  # SNI + cert check use the hostname


@pytest.mark.asyncio
async def test_fetch_script_blocks_dns_rebinding(monkeypatch):
    """TOCTOU regression: DNS flips public -> internal between the pre-flight
    check and connect time. The pinned handler re-resolves and must refuse —
    and nothing may open a socket."""
    answers = iter(["93.184.216.34", "127.0.0.1"])

    def _flipping_dns(host, port, *args, **kwargs):
        ip = next(answers, "127.0.0.1")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    def _no_connect(*args, **kwargs):
        raise AssertionError("socket must not be opened for a rebinding host")

    monkeypatch.setattr(socket, "getaddrinfo", _flipping_dns)
    monkeypatch.setattr(socket, "create_connection", _no_connect)

    result = await fetch_script("https://rebind.example.com/x.sh")

    assert not result.success
    assert "blocked" in result.error.lower() or "private" in result.error.lower()
