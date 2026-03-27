# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for secret detection

"""Tests for the real-time secret detector."""

import pytest

from ridincligun.advisory.secret_detector import detect_secrets

# ── API key detection ──────────────────────────────────────────────

@pytest.mark.parametrize(
    "command,expected_kind",
    [
        (
            "curl -H 'Authorization: Bearer sk-ant-api03-abc123def456ghi789jkl012mno345'"
            " https://api.example.com",
            "api_key",
        ),
        ("export OPENAI_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890", "api_key"),
        ("echo ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789", "api_key"),
        ("GH_TOKEN=gho_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789 gh pr list", "api_key"),
        ("export TOKEN=github_pat_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdef", "api_key"),
        ("SLACK_TOKEN=xoxb-123456789-abcdefghij-zyxwvutsrq", "api_key"),
        ("aws configure set aws_access_key_id AKIAIOSFODNN7EXAMPLE", "api_key"),
        (
            "gcloud auth activate-service-account"
            " --key AIzaSyA1234567890abcdefghijklmnopqrstuvwx",
            "api_key",
        ),
        ("GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx", "api_key"),
        ("echo npm_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789", "api_key"),
        ("twine upload --token pypi-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789", "api_key"),
    ],
)
def test_detects_api_keys(command: str, expected_kind: str) -> None:
    result = detect_secrets(command)
    assert result.has_secrets
    kinds = {m.kind for m in result.matches}
    assert expected_kind in kinds


# ── Password flags ─────────────────────────────────────────────────

@pytest.mark.parametrize(
    "command",
    [
        "mysql -u root -pMySecretPass123",
        "mysql -u root -p 'MySecretPass123'",
        'sshpass -p "hunter2" ssh user@host',
        "psql --password=supersecret host",
    ],
)
def test_detects_password_flags(command: str) -> None:
    result = detect_secrets(command)
    assert result.has_secrets
    kinds = {m.kind for m in result.matches}
    assert "password_flag" in kinds


# ── Credential URLs ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "command",
    [
        "git clone https://user:token@github.com/org/repo.git",
        "curl https://admin:password@internal.example.com/api",
        "psql postgres://dbuser:s3cret@db.host:5432/mydb",
    ],
)
def test_detects_credential_urls(command: str) -> None:
    result = detect_secrets(command)
    assert result.has_secrets
    kinds = {m.kind for m in result.matches}
    assert "credential_url" in kinds


# ── Env secret assignments ─────────────────────────────────────────

@pytest.mark.parametrize(
    "command",
    [
        "export ANTHROPIC_API_KEY=sk-ant-api03-realkey123456",
        "export DATABASE_PASSWORD=verylongsecretvalue",
        "MY_AUTH_TOKEN=abcdef1234567890 ./run.sh",
        "SECRET_KEY=mysupersecretkey1234 python app.py",
    ],
)
def test_detects_env_secrets(command: str) -> None:
    result = detect_secrets(command)
    assert result.has_secrets
    kinds = {m.kind for m in result.matches}
    # May match as api_key or env_secret depending on value format
    assert kinds & {"env_secret", "api_key"}


# ── Private key content ────────────────────────────────────────────

def test_detects_private_key() -> None:
    command = "echo '-----BEGIN RSA PRIVATE KEY-----' > /tmp/key.pem"
    result = detect_secrets(command)
    assert result.has_secrets
    kinds = {m.kind for m in result.matches}
    assert "private_key" in kinds


# ── Authorization headers ──────────────────────────────────────────

def test_detects_auth_header() -> None:
    command = "curl -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0' https://api.example.com"
    result = detect_secrets(command)
    assert result.has_secrets
    kinds = {m.kind for m in result.matches}
    assert "auth_header" in kinds


# ── Safe commands (no false positives) ─────────────────────────────

@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "git status",
        "grep -r password_field src/",
        "cat /etc/hostname",
        "echo hello world",
        "export PATH=/usr/local/bin:$PATH",
        "docker run -p 8080:80 nginx",
        "curl https://example.com",
        "ssh user@host",
        "pip install requests",
        "npm install",
        "-p 80",  # short -p value (port, not password)
    ],
)
def test_safe_commands_no_false_positives(command: str) -> None:
    result = detect_secrets(command)
    assert not result.has_secrets, f"False positive on: {command}, matches: {result.matches}"


# ── Empty / blank input ────────────────────────────────────────────

@pytest.mark.parametrize("command", ["", "   ", None])
def test_empty_input(command: str | None) -> None:
    result = detect_secrets(command or "")
    assert not result.has_secrets


# ── Deduplication ──────────────────────────────────────────────────

def test_deduplicates_by_kind() -> None:
    """Multiple API keys in one command should produce one api_key match."""
    command = "FOO=sk-abc12345678901234567890 BAR=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"
    result = detect_secrets(command)
    assert result.has_secrets
    api_key_matches = [m for m in result.matches if m.kind == "api_key"]
    assert len(api_key_matches) == 1
