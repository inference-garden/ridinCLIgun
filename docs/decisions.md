# Decisions

Numbered, dated, append-only. Each decision is stable once recorded.

---

### D001 — 2026-03-15: Tech stack
Python 3.12+, Textual for TUI, pyte for terminal emulation, PTY-backed shell.

### D002 — 2026-03-15: Config location
`~/.config/ridincligun/` with `.env` for API secrets, `config.toml` for settings.

### D003 — 2026-03-15: AI provider strategy
Start with Anthropic API. Add OpenAI and Mistral later. Abstract adapter pattern for any LLM.

### D004 — 2026-03-15: UI layout
60/40 split (shell/advisory), movable divider. Minimal tags status bar. Colored block warnings.

### D005 — 2026-03-15: Shortcut model
macOS-native Cmd+C/V/Q where possible. Ctrl+G as leader key for app-specific actions. Never steal shell-native keys.

### D006 — 2026-03-15: Platform priority
macOS first. Linux and Windows later once stable.

### D007 — 2026-03-15: Distribution
Python package (pip install) first. Homebrew later.

### D008 — 2026-03-15: No database
Config.toml, command_catalog.json, plain text logs. No SQLite unless strong need arises.
