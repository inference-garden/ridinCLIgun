# Security Model

How ridinCLIgun handles your data, your commands, and your secrets.

## Principles

- **Advises, never acts** — ridinCLIgun never modifies, executes, or blocks your commands
- **Local-first** — works fully offline with no AI provider configured
- **AI is opt-in** — you toggle it on, you trigger reviews, you confirm what gets sent

## What is sent to the AI

When you request an AI review (`Ctrl+G, R`):

- **Preserved:** command structure (so the AI can give accurate analysis)
- **Redacted:** secrets, API keys, sensitive file paths
- **Never sent:** file contents, environment variables, shell history
- **Preview available:** see exactly what will be sent before it leaves

## Security layers

| Layer | What it does |
|-------|-------------|
| Real-time secret detection | Scans every keystroke; blocks AI automatically when secrets are found |
| Privacy-only sanitization | Redacts secrets and sensitive paths before sending to AI |
| Redaction preview | Shows you the redacted command before it's sent |
| Secret mode (`Ctrl+G, S`) | Manual kill-switch — blocks all AI communication |
| In-flight guard | Discards AI responses if secret mode is toggled during a request |
| Environment isolation | API keys are stripped from the embedded shell environment |

## Known limits

- Pattern matching is best-effort, not a guarantee
- Does not deeply parse shell syntax (no AST)
- Cannot catch novel or obfuscated credential formats
- See [Command Analysis](command_analysis.md) for detailed analysis gaps

## What the AI sees — full prompt transparency

ridinCLIgun sends exactly two things to the AI provider: a **system prompt** and
a **user message**. Nothing else — no history, no context, no environment data.

### System prompt (sent with every review)

```
You are a technical shell command reviewer in a developer tool called ridinCLIgun.

Your job: classify shell commands by risk and explain them factually.

Rules:
- You only describe and classify. You never execute anything.
- Use clinical, neutral language. No dramatic descriptions of consequences.
- Classify risk as: "safe", "caution", "warning", or "danger".
- For dangerous commands, state the risk factually without graphic detail.
- Suggest safer alternatives when applicable.
- Keep responses short — displayed in a narrow side panel.
- Commands may contain placeholders like [SENSITIVE_FILE] or [REDACTED] —
  these represent privacy-redacted values. Treat them as their real equivalents.
- If the command contains what appears to be a real API key, password, token,
  or credential (not a placeholder), flag this immediately and advise the
  user to rotate it.

Response format (exact headers):
RISK: <safe|caution|warning|danger>
SUMMARY: <one-line factual description>
EXPLANATION: <why this risk level, 1-3 short sentences>
SUGGESTION: <a concrete safer command, or "None" if already safe>
```

### User message (per review request)

```
Classify this shell command:
\```
<your command, after sanitization>
\```
```

### Deep script analysis (Layer 3 — automatic when triggered)

When a command pipes a remote script to a shell (e.g. `curl ... | bash`), ridinCLIgun
fetches the script and sends it for a separate analysis. This uses a different prompt:

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

The user message includes the download URL and the fetched script content
(truncated at 64 KB if too large).

### Summary

The AI receives either a single command or a fetched script — never both at once,
never with history, never with environment data.

## AI prompt safety net

The system prompt includes an explicit instruction to flag real credentials
that slip past the sanitization filters — and advise immediate rotation.
This is a last line of defense, not a primary control.

---

*This document reflects the security posture of v0.3.*
