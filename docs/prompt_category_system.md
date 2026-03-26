# Prompt Category System

## Overview

ridinCLIgun uses a **category-aware prompt system** to give AI reviews that are specific to what the command actually does. Instead of one generic "classify this command" instruction, the AI receives domain-specific guidance based on the command's category.

---

## How it works

1. **The user types a command** in the terminal.
2. **The local advisory engine** matches the command against 17 known command families (rm, chmod, git, curl, etc.).
3. **The prompt builder** maps matched families to one of 6 prompt categories.
4. **The AI receives** the base system prompt + a category-specific supplement that steers it toward relevant advice.
5. **If no family matches**, the command falls into the General category — the AI still reviews it, but with the base prompt only (no category supplement). This is the most common case for everyday commands like `ls`, `cd`, `echo`, etc.

---

## Prompt categories

| Category | What it covers | AI focus |
|----------|---------------|----------|
| **File operations** | rm, chmod, mkfs, disk overwrite, dd | Data loss, permissions, recovery, dry-run alternatives |
| **Network & downloads** | curl-pipe, network, SSH/keys, firewall | Trust verification, exposure surface, download-then-inspect |
| **Git & version control** | Destructive git operations | History rewriting, upstream impact, reflog recovery |
| **Package & system** | Package managers, system files, Docker, sudo | Supply chain, system stability, privilege scope |
| **Secrets & environment** | Env secrets, history-sensitive | Credential rotation, exposure surface, log hygiene |
| **General** (fallback) | Everything not matched above | Standard review — risk classification without domain hints |

Categories are selected **automatically** — the user never needs to think about prompt internals.

---

## Modes

The AI's tone adapts based on the selected mode:

| Mode | Tone | Intended audience |
|------|------|-------------------|
| **Default** | Clinical, neutral, factual | Developers |
| **Explorer mode (for Kids)** | Friendly, encouraging, simple analogies | Curious kids age 10–12 learning the terminal |

Modes are independent of language — Explorer mode in German works the same as in English.

---

## User settings

Three settings control AI review behavior (accessible via Settings menu):

- **Mode** — Default / Explorer mode (for Kids)
- **Detail level** — Brief / Standard / Detailed *(planned)*
- **Language** — EN / DE / FR *(planned, see i18n feature)*

---

## Storage

Prompt templates are stored in `data/prompt_templates.toml` alongside the existing command catalog. TOML was chosen over JSON for human-readable multiline prompt strings.

---

## Prompt inventory

All prompts and prompt components used in the system, listed by layer.

### Layer 2 — Command review (standard AI review via Ctrl+G, R)

| Component | Location | Purpose |
|-----------|----------|---------|
| **Base system prompt** | `provider/prompt.py` → `_BASE_SYSTEM_PROMPT` | Role definition, response format (RISK/SUMMARY/EXPLANATION/SUGGESTION), credential detection rule, placeholder handling, self-check quality gate |
| **Category supplement: file_ops** | `data/prompt_templates.toml` → `[categories.file_ops]` | Data loss focus, dry-run flags, trash/backup alternatives |
| **Category supplement: network** | `data/prompt_templates.toml` → `[categories.network]` | Exposure surface, download-then-inspect, TLS, lockout risk |
| **Category supplement: git** | `data/prompt_templates.toml` → `[categories.git]` | History rewriting, upstream impact, reflog recovery |
| **Category supplement: package_system** | `data/prompt_templates.toml` → `[categories.package_system]` | Privilege scope, supply chain trust, host mounts |
| **Category supplement: secrets** | `data/prompt_templates.toml` → `[categories.secrets]` | Credential rotation, history/log exposure, secure alternatives |
| **Category supplement: general** | `data/prompt_templates.toml` → `[categories.general]` | Empty — base prompt only, no domain hints |
| **Mode supplement: default** | `data/prompt_templates.toml` → `[modes.default]` | Empty — base tone (clinical, factual) |
| **Mode supplement: explorer** | `data/prompt_templates.toml` → `[modes.explorer]` | Kid-friendly tone, analogies, encouragement, "Did you know?" |
| **User message** | `provider/prompt.py` → `build_review_prompt()` | Wraps sanitized command in code block, optional context |

### Layer 3 — Deep script analysis (auto-triggered for curl|bash)

| Component | Location | Purpose |
|-----------|----------|---------|
| **Deep analysis system prompt** | `provider/deep_analysis.py` → `DEEP_ANALYSIS_SYSTEM` | Script analyzer role, action listing, obfuscation flags, response format (RISK/SUMMARY/ACTIONS/CONCERNS) |
| **Deep analysis user message** | `provider/deep_analysis.py` → `build_deep_analysis_prompt()` | URL + script content + truncation note |

### Sanitization (pre-send)

| Component | Location | Purpose |
|-----------|----------|---------|
| **Command sanitizer** | `provider/prompt.py` → `_sanitize_command()` | Redacts sensitive file paths and inline secrets before sending to AI |

### Composition order

The full system prompt sent to the AI is assembled as:

```
1. Base system prompt          (always)
2. + Category supplement       (if command matched a known family)
3. + Mode supplement           (if mode ≠ default)
```

Deep analysis uses its own separate system prompt (`DEEP_ANALYSIS_SYSTEM`), not the composed command-review prompt.

---

## Full prompt texts

Verbatim prompts as sent to the AI. These are the actual strings assembled at runtime.

### Base system prompt (Layer 2 — always included)

```
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

### Category supplements

Appended after `Category-specific guidance:` when the command matches a known family.

#### file_ops

```
Focus on: data loss risk, recoverability, safer alternatives.
Always suggest a dry-run or preview flag if one exists (e.g. rm -i, chmod --changes).
If recursive, warn about scope and suggest limiting the target path.
Mention trash/backup as alternatives to permanent deletion when applicable.
```

#### network

```
Focus on: what gets exposed, to whom, over what channel.
For piped downloads (curl|sh): suggest download-then-inspect workflow.
For SSH operations: flag key permission issues and agent forwarding risks.
For firewall changes: flag lockout risk and suggest testing rules before applying.
Mention TLS/plaintext distinction when relevant.
```

#### git

```
Focus on: history rewriting, upstream impact, team consequences.
Mention reflog as a recovery mechanism for local operations.
Distinguish local-only vs. pushed changes — pushed rewrites affect others.
Suggest --dry-run or --no-push alternatives when available.
```

#### package_system

```
Focus on: privilege scope, system stability, supply chain trust.
For sudo: clarify what runs as root and whether elevation is necessary.
For package managers: flag unverified sources or --force/--no-verify flags.
For Docker: flag privileged mode, host mounts, and network exposure.
For system file edits: warn about boot/config breakage.
```

#### secrets

```
Focus on: credential exposure surface and rotation urgency.
Flag if secrets may land in shell history, logs, or process listings.
Suggest secure alternatives (env files, secret managers, --from-file).
If a credential appears in the command, advise immediate rotation.
```

#### general

*(empty — base prompt only, no category supplement appended)*

### Mode supplements

Appended after `Tone and audience:` when mode is not default.

#### default

*(empty — clinical, factual tone from the base prompt)*

#### explorer (for Kids)

```
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

### Deep analysis system prompt (Layer 3)

Used for curl|bash-style commands. Separate from the Layer 2 composition.

```
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
```

### Deep analysis user message (truncated script variant)

When a fetched script exceeds the model's context window capacity, this preamble is prepended:

```
IMPORTANT: This script was truncated to fit the model's context window.
You are seeing only the first part. Your analysis is INCOMPLETE. State
this clearly in your SUMMARY (e.g. 'Partial analysis — script truncated').
Flag in CONCERNS that unreviewed code may contain additional actions.
```

