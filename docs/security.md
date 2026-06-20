# Security Model

This document covers data flow, trust boundaries, local storage, controls, and known limits. Trigger rules live in `command_analysis.md`; prompt composition lives in `prompt_category_system.md`.

## Principles

- ridinCLIgun advises; it does not execute, rewrite, or block shell commands.
- The offline advisory features work without any AI provider configured.
- AI traffic is user-controlled, but not limited to `F2` alone: provider validation can also make a minimal test request.

## When network traffic can happen

| Flow | Trigger | What leaves the machine | What does not |
|------|---------|-------------------------|---------------|
| Provider validation | AI is toggled on with `F4`, or a provider switch completes while a valid key is already available | a minimal review request for `echo test` | current shell command, shell history, file contents, environment variables |
| Layer 2 AI review | AI is enabled, a provider is configured, and the user presses `F2` | composed Layer 2 system prompt, current command after privacy redaction, locale instruction when active language is not English | file contents, shell history, shell output / scrollback, review history, environment variables |
| Layer 3 deep analysis | after Layer 2, when the reviewed command matches a remote-execute pattern such as `curl ... | bash` | fetched download URL, fetched script content, possible truncation warning, locale instruction when active language is not English | fetched content is never executed by ridinCLIgun |

Layer 3 trust boundary sequence:

1. ridinCLIgun fetches the remote URL from the local machine
2. the fetched script content is then sent to the AI provider for analysis

## Local storage

| Path | Purpose | Notes |
|------|---------|-------|
| `~/.config/ridincligun/config.toml` | app settings | created on first run |
| `~/.config/ridincligun/.env` | API keys | owner-only permissions (`0600`) |
| `~/.config/ridincligun/history.jsonl` | AI review and deep-analysis history | owner-only permissions (`0600`) |
| bundled `data/` files | command catalog, prompt templates, locales | shipped with the app |

`history.jsonl` currently stores:

- timestamp
- raw command text
- source (`ai` or `deep_analysis`)
- risk
- summary
- explanation
- suggestion
- provider name
- token counts

That history stays local, but it is privacy-relevant because reviewed commands are stored verbatim.

## Current controls

- **Secret detection while typing**: if the current command looks secret-bearing, review is interrupted and the user must confirm explicitly before anything is sent.
- **Redaction preview**: when sanitization changes the command and preview is enabled, the app shows original vs. redacted text first. A second `F2` confirms the send.
- **Secret Mode (`F5`)**: suppresses AI reviews and discards stale in-flight results.
- **Environment isolation**: API keys are loaded into app memory and passed explicitly to provider adapters; they are not injected into the embedded shell environment.
- **Permission hardening**: `.env` and `history.jsonl` are kept owner-readable/writable only.

## Known limits and current gaps

- Secret detection and sanitization are best-effort regex-based checks, not a shell parser.
- Only matched secret patterns and a small set of sensitive file paths are redacted. Arbitrary filenames, hostnames, URLs, and user data are preserved.
- The AI sees command structure intentionally; dangerous targets such as `/dev/...`, `rm -rf`, or pipe chains are not masked.
- Deep analysis only covers specific download-and-execute patterns. It does not model multi-step attack chains across separate commands.
- Layer 3 fetch hardening (`B-S09`, closed in v0.4.4): HTTPS-only, the resolved IP must be public (loopback/private/link-local/reserved and the `169.254.169.254` metadata endpoint are refused), redirects are re-validated on every hop, and Secret Mode is checked **before** the fetch so toggling it cancels the request. Residual: DNS rebinding is not fully prevented (the IP is re-resolved at connect time).
- Scripts behind authentication, stdin-fed content, heredocs, and shell sourcing flows are outside current deep-analysis coverage.

 .
