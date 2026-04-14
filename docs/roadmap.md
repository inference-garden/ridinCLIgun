# Roadmap

Where ridinCLIgun is heading. Vision, not promises — this is a personal project
with no fixed timeline.

## v0.3 — "This tool is careful." ✅ shipped 2026-03-21

Settings UI, toast notifications, clipboard safety, onboarding flow,
AI review with redaction preview, deep script analysis, API key management,
CI pipeline, security hardening.

## v0.4 — "This tool is genuinely useful." ✅ shipped 2026-04-14

**Offline command knowledge:**
- 6,600+ command catalog (tldr-pages v2.3, MIT) — real examples in the advisory pane as you type
- Typo detection — suggests `git` when you type `gti`
- German and French locale overlays for the catalog

**Smarter AI:**
- Per-category prompt templates — concrete suggestions, not just "be careful"
- AI responds in your language (EN/DE/FR)
- Explorer mode — gentler tone for beginners and kids

**Better experience:**
- History browser (`Ctrl+G, K`) — browse, search, and revisit past AI reviews
- Full UI in English, German, or French
- Provider/model switching persists across restarts
- Provider and model configurable directly from the Settings screen

## v0.5 — "This tool thinks with me." (planned)

The advisory pane gets interactive. AI responses appear as they stream. You can
follow up in plain language without leaving the terminal.

- **Streaming AI responses** — token-by-token display, no more waiting for the full answer
- **Conversational follow-up** — after any review, ask "why?", "what if I add -v?", "show me a safer way" — without running a new review
- **Approval tiers** — safe commands auto-dismiss, dangerous ones persist until you acknowledge
- **Per-command context** — inject working directory, git branch, and recent history into AI prompts for smarter, more relevant answers
- **Session memory** — AI knows what you've already run this session; avoids repeating itself
- **Scrollbar indicators** in advisory and shell panes
- **Cost awareness** — running token count so you know what you're spending

Deferred from v0.4: approval tiers, streaming, per-command context, local AI review cache.

## v0.6 — "This tool teaches." (planned)

ridinCLIgun started as a safety tool for people who are curious about the terminal
but afraid of it. This version leans into that identity.

- **Learning game** — guided terminal challenges with a real shell, hints, and validation. No simulators.
  Designed for kids and beginners. This is one of the original reasons this project exists.
- **Linux support** — the PTY layer is already POSIX; this is testing + packaging
- **Homebrew / pipx distribution** — install without cloning a repo
- **Custom risk catalogs** — team-defined or instructor-defined warning patterns, shareable as TOML files. Useful for bootcamps and compliance teams.
- **OS-aware advisory** — "on macOS, `-i` behaves differently than GNU `sed`"

## v1.0 — "This tool runs your workflows." (vision)

The terminal becomes a cockpit. External AI agents can propose commands; you approve,
edit, or reject before anything runs. You stay in control — always.

- **Agent cockpit** — queue of agent-proposed commands with full context. Approve/reject/edit.
  The agent never gets direct shell access. The human is always the last mile.
- **Multi-agent integration** — Claude Code, OpenAI Agents, and similar systems as
  first-class inputs. ridinCLIgun as the human-in-the-loop gate for AI-driven workflows.
- **Full session audit log** — what was proposed, what you approved, what ran, what the output was.
  Exportable, local-only.
- **Workflow templates** — reusable multi-step recipes you define and re-run safely.

---

## Parking lot

Ideas without a version slot yet:

- VS Code terminal integration
- Gamified lesson editor — let instructors contribute challenges in a standard format
- Accessibility — screen reader compatibility evaluation
- Dependency pinning + reproducible builds (target v1.0)

---

*Updated when milestones ship.*
