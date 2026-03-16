# ridinCLIgun

A terminal companion that advises but never acts.

## What is it?

ridinCLIgun is a split-pane terminal app: a real shell on the left, an advisory assistant on the right. It warns you about dangerous commands, offers AI-powered reviews, and helps you work in the terminal more safely — without ever taking control away from you.

**Key principle: the advisor never executes anything. You stay in charge.**

## Status

v0.2 — Early release. macOS only. Python 3.12+.

## Features

- Real PTY shell with full color, tab completion, and history
- Local command warnings (offline, instant) from a built-in catalog
- AI command review via Anthropic Claude (opt-in, explicit trigger)
- Secret mode — blocks any command from being sent to AI
- Resizable split-pane layout (60/40 default)
- Mouse text selection + clipboard copy from both panes
- Ctrl+G leader key for all app shortcuts

## Quick start

```bash
# Clone and install
git clone <repo-url>
cd ridinCLIgun
pip install -e ".[all]"

# Run
python -m ridincligun
```

### Optional: AI review

To use AI-powered command review, add your API key:

```bash
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" >> ~/.config/ridincligun/.env
```

Then toggle AI on inside the app with `Ctrl+G, A`.

## Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Q` | Quit |
| `F6` / `F7` | Move divider left / right |
| `Ctrl+G, R` | AI review current command |
| `Ctrl+G, A` | Toggle AI on/off |
| `Ctrl+G, S` | Toggle Secret mode |
| `Ctrl+G, C` | Copy selected text |
| `Ctrl+G, V` | Paste from clipboard |
| `Ctrl+G, X` | Restart shell |
| `Ctrl+G, D` | Debug info |
| `Ctrl+G, H` | Show all shortcuts |

## Configuration

Config lives in `~/.config/ridincligun/`:

- `config.toml` — UI and provider settings
- `.env` — API keys (never committed)

## Development

```bash
# Install with dev deps
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/
```

## License

GPL-3.0-or-later — see [LICENSE](LICENSE)
