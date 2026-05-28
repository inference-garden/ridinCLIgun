# Prompt Category System

This document covers Layer 2 prompt composition, category mapping, and current Layer 3 wiring. Trigger rules live in `command_analysis.md`; data-flow implications live in `security.md`.

## Layer 2 composition

Layer 2 command review uses three prompt inputs:

1. base system prompt
2. category supplement
3. mode supplement

If the active language is not English, a language instruction is also appended to the system prompt.

Source of truth:

- `src/ridincligun/provider/prompt.py`
- `data/prompt_templates.toml`
- `src/ridincligun/provider/deep_analysis.py`

The provider user message then contains:

- a fixed leading line: `Classify this shell command:`
- a fenced code block containing the sanitized command

If the active language is not English, the request also carries a short locale-enforcement context line.

## Base system prompt

Current job of the base prompt:

- classify risk as `safe`, `caution`, `warning`, or `danger`
- produce `SUMMARY`, `EXPLANATION`, and `SUGGESTION`
- stay concise for the narrow advisory pane
- treat `[SENSITIVE_FILE]` and `[REDACTED]` as real redactions
- flag any credential that appears to have slipped through

## Category mapping

17 local command families currently map to 6 prompt categories.

| Category | Family ids | Current focus |
|----------|------------|---------------|
| `file_ops` | `rm`, `chmod`, `mkfs`, `disk_overwrite`, `dd` | data loss, recoverability, safer alternatives |
| `network` | `curl_pipe`, `network`, `ssh_and_keys`, `iptables_firewall` | exposure surface, download-then-inspect, network lockout risk |
| `git` | `git_destructive` | history rewriting, upstream impact, reflog recovery |
| `package_system` | `package_managers`, `system_files`, `docker`, `sudo` | privilege scope, supply chain, system stability |
| `secrets` | `env_secrets`, `history_sensitive` | credential exposure, rotation urgency, history/log hygiene |
| `general` | none | base prompt only |

Category resolution stops at the first matching category in template order.

## Modes

Current review modes:

| Mode | Effect |
|------|--------|
| `default` | no extra tone supplement |
| `explorer` | simpler language, analogies, encouragement, beginner/kid-oriented tone |

`language` and `review_mode` are independent settings.

## Current Layer 2 language behavior

When locale is `de` or `fr`:

- the system prompt adds an instruction to keep `RISK / SUMMARY / EXPLANATION / SUGGESTION` headers in English but write content in the selected language
- the request context adds a second, shorter locale reminder for weaker models

English adds no locale instruction.

## Sanitization before Layer 2 send

Current sanitizer behavior:

- redacts a small set of sensitive file paths such as `~/.ssh/...`, `~/.aws/...`, `/etc/shadow`, `~/.netrc`, `~/.pgpass`
- redacts inline `export ...SECRET...=value`-style patterns
- preserves dangerous structure such as targets, flags, pipes, and devices

This is privacy-oriented redaction, not semantic command rewriting.

## Current Layer 3 wiring

Layer 3 currently does **not** use the documented separate deep-analysis system prompt in live provider calls.

Current implementation path:

- `build_deep_analysis_prompt()` creates a payload with the download URL, optional truncation warning, optional locale instruction, and fetched script content
- that payload is passed through the normal provider review interface
- provider adapters wrap it again with the normal Layer 2 user-message envelope
- the request context is set to `deep_script_analysis`
- no custom Layer 3 system prompt is injected into the provider call

In other words, the current live Layer 3 call path is:

- system prompt: the adapter fallback base prompt
- user message: the deep-analysis payload wrapped as if it were the reviewed "command"

## Unused / not currently wired

The codebase currently contains:

- `DEEP_ANALYSIS_SYSTEM` in `provider/deep_analysis.py`

That constant documents an intended dedicated Layer 3 system prompt, but it is not currently passed to the adapters in the live review path.

 