# Prompt Category System


This document covers
 -Layer 2 prompt composition,
 - category mapping,
 - - and Layer 3 wiring.
 Trigger rules live in `command_analysis.md`; data-flow implications live in `security.md`.

## Layer 2 composition

Layer 2 command review composes its **system prompt** from:

1. base system prompt
2. category supplement (from the resolved prompt category)
3. mode supplement (`default` / `explorer`)
4. a language instruction (appended **last**) when the active locale is not English

The provider **user message** then contains:

- a fixed leading line: `Classify this shell command:`
- a fenced code block with the sanitized command
- for non-English locales, a short locale-enforcement context line (a second reminder for weaker
  models)

Source of truth: `src/ridincligun/provider/prompt.py`, `data/prompt_templates.toml`,
`src/ridincligun/provider/deep_analysis.py`.

## Category mapping

The catalog's command families map to 6 prompt categories:

| Category | Family ids | Focus |
|----------|------------|-------|
| `file_ops` | `rm`, `chmod`, `mkfs`, `disk_overwrite`, `dd` | data loss, recoverability, safer alternatives |
| `network` | `curl_pipe`, `network`, `ssh_and_keys`, `iptables_firewall` | exposure surface, download-then-inspect, lockout risk |
| `git` | `git_destructive` | history rewriting, upstream impact, reflog recovery |
| `package_system` | `package_managers`, `system_files`, `docker`, `sudo` | privilege scope, supply chain, system stability |
| `secrets` | `env_secrets`, `history_sensitive` | credential exposure, rotation urgency, history/log hygiene |
| `general` | none | base prompt only |

Resolution returns the first matching category in template order (`resolve_category`).

**v0.4.7 change — resolved once:** the category is now computed a single time inside `CommandFacts`
(`build_command_facts`) and reused for the Layer-2 prompt **and** the Layer-3 decision. There is no
separate per-layer re-resolution, so the catalog and the deep-analysis path can no longer drift.

## Modes

| Mode | Effect |
|------|--------|
| `default` | no extra tone supplement |
| `explorer` | simpler language, analogies, encouragement, beginner/kid-oriented tone |

`language` and `review_mode` are independent settings. The mode supplement is shared by the Layer 2
and Layer 3 system prompts (same voice in both).

## Language behavior

When locale is `de` or `fr`:

- the system prompt appends an instruction to keep the `RISK / SUMMARY / EXPLANATION / SUGGESTION` headers in English but write the **content** in the selected language, reinforced by a directive written in that language itself (recency + native phrasing help weaker models — Haiku, Mistral Small)
- the user-message context adds a second, shorter locale reminder

English adds no locale instruction.

## Sanitization before send

- redacts a small set of sensitive file paths (`~/.ssh/…`, `~/.aws/…`, `~/.gnupg/…`,
  `/etc/shadow`, `~/.netrc`, `~/.pgpass`)
- redacts inline `export …SECRET…=value`-style assignments → `[REDACTED]`
- preserves dangerous structure (targets, flags, pipes, devices) so risk stays assessable

Privacy-oriented redaction, not semantic rewriting. The real-time secret detector
(`advisory/secret_detector.py`) is the primary defence; this is a secondary net.

## Layer 3 wiring (current)

Layer 3 (deep analysis of a fetched remote script) runs on a **dedicated** system prompt
(`build_deep_analysis_system_prompt`, base `DEEP_ANALYSIS_SYSTEM`) — a script-security-analyzer role,
**not** the Layer 2 category prompt — and (v0.4.7) always on the provider's **Deep** model. The
response format stays `RISK / SUMMARY / EXPLANATION / SUGGESTION` so the shared adapter parser reads
it (an earlier `ACTIONS/CONCERNS` format was silently dropped; `tests/test_deep_analysis.py` pins the
compatibility). Mode and language are composed in exactly as for Layer 2.

The active tier + model (`Fast · <id>` / `Deep · <id>`) is shown on every review.

---

# Appendix — actual prompts (verbatim, as sent to the provider)

These are reproduced from source; keep in sync if the source changes.

## A1 — Layer 2 base system prompt (`_BASE_SYSTEM_PROMPT`)

```text
You are a technical shell command reviewer in a developer tool called ridinCLIgun.

Your job: classify shell commands by risk and explain them factually.

Rules:
- You only describe and classify. You never execute anything.
- Classify risk as: "safe", "caution", "warning", or "danger".
- Suggest safer alternatives when applicable. For non-safe commands, provide
  a concrete safer alternative command that achieves a similar goal.
- Keep responses short — displayed in a narrow side panel.
- Commands may contain placeholders like [SENSITIVE_FILE] or [REDACTED] — these
  represent privacy-redacted values. Treat them as their real equivalents.
- If the command contains what appears to be a real API key, password, token,
  or credential (not a placeholder), flag this immediately in your response
  and advise the user to rotate it. This is a critical safety check.

Response format (use exactly these headers):
RISK: <safe|caution|warning|danger>
SUMMARY: <one-line factual description>
EXPLANATION: <why this risk level, 1-3 short sentences>
SUGGESTION: <a concrete safer/better command, or "None" if the command is already safe>

Before responding, verify internally:
1. Warnings are specific to the actual flags/arguments passed — not generic.
2. Risk level matches the real danger — do not over-warn safe commands.
3. No unnecessary explanations — be concise.
```

## A2 — Category supplements (appended after the base prompt, when a non-`general` category matches)

Prefixed in the prompt by a line `Category-specific guidance:`.

**`file_ops`:**
```text
Focus on: data loss risk, recoverability, safer alternatives.
Always suggest a dry-run or preview flag if one exists (e.g. rm -i, chmod --changes).
If recursive, warn about scope and suggest limiting the target path.
Mention trash/backup as alternatives to permanent deletion when applicable.
```

**`network`:**
```text
Focus on: what gets exposed, to whom, over what channel.
For piped downloads (curl|sh): suggest download-then-inspect workflow.
For SSH operations: flag key permission issues and agent forwarding risks.
For firewall changes: flag lockout risk and suggest testing rules before applying.
Mention TLS/plaintext distinction when relevant.
```

**`git`:**
```text
Focus on: history rewriting, upstream impact, team consequences.
Mention reflog as a recovery mechanism for local operations.
Distinguish local-only vs. pushed changes — pushed rewrites affect others.
Suggest --dry-run or --no-push alternatives when available.
```

**`package_system`:**
```text
Focus on: privilege scope, system stability, supply chain trust.
For sudo: clarify what runs as root and whether elevation is necessary.
For package managers: flag unverified sources or --force/--no-verify flags.
For Docker: flag privileged mode, host mounts, and network exposure.
For system file edits: warn about boot/config breakage.
```

**`secrets`:**
```text
Focus on: credential exposure surface and rotation urgency.
Flag if secrets may land in shell history, logs, or process listings.
Suggest secure alternatives (env files, secret managers, --from-file).
If a credential appears in the command, advise immediate rotation.
```

**`general`:** no supplement (base prompt only).

## A3 — Mode supplements (appended under `Tone and audience:`)

**`default`:** no supplement.

**`explorer`:**
```text
Explain like talking to a smart, curious 10-year-old who is learning the terminal.
Use simple words and short sentences. Use everyday analogies:
- files and folders = papers in a filing cabinet
- permissions = locks and keys
- root/sudo = the master key that opens everything
- pipes = connecting tubes that pass water (data) from one tool to the next
- network = sending a letter to another computer
No jargon without a brief explanation in parentheses.
Keep it encouraging — mistakes are how you learn.
If something is dangerous, say so clearly but without scaring.
When a command is safe, say something positive like "Good one!" or "This is a handy command."
End with a short "Did you know?" fun fact about the command or concept when you can.
```

## A4 — Language instruction (system prompt, appended last for `de`/`fr`)

```text
IMPORTANT: Write all SUMMARY, EXPLANATION, and SUGGESTION content in <Language>. Keep the response
format headers (RISK, SUMMARY, EXPLANATION, SUGGESTION) in English.
<native directive>
```
- `<Language>` = `German` / `French`.
- native directive (`de`): `Schreibe deine gesamte Antwort (SUMMARY, EXPLANATION, SUGGESTION) auf Deutsch.`
- native directive (`fr`): `Rédige toute ta réponse (SUMMARY, EXPLANATION, SUGGESTION) en français.`

## A5 — Layer 2 user message (`build_review_prompt`)

````text
Classify this shell command:
```
<sanitized command>
```
````
For `de`/`fr`, a context line is also sent (`build_locale_context`):
```text
IMPORTANT: You MUST write all response content (SUMMARY, EXPLANATION, SUGGESTION) in <Language>
only. Do not use English in those fields. <native directive>
```

## A6 — Layer 3 deep-analysis system prompt (`DEEP_ANALYSIS_SYSTEM`)

```text
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
```
(mode + language composed in exactly as A3 / A4.)

## A7 — Layer 3 user payload (`build_deep_analysis_prompt`)

````text
Analyze this script downloaded from: <url>

[if truncated: IMPORTANT: This script was truncated to fit the analysis window. You are
seeing only the first part. Your analysis is INCOMPLETE. State this clearly in your SUMMARY
(e.g. 'Partial analysis — script truncated'). Flag in CONCERNS that unreviewed code may
contain additional actions.]

[if de/fr: the A4-style language line]
```
<fetched script content>
```
````
