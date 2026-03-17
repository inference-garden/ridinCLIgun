# ridinCLIgun

> Your terminal copilot that watches, warns, but never touches the wheel.

```
 ┌─ Shell ─────────────────────────┐┌─ Advisory ──────────────┐
 │ $ rm -rf ~/Documents            ││ ⚠ DANGER               │
 │                                 ││ Recursive forced delete │
 │                                 ││ targeting home folder.  │
 │                                 ││                         │
 │                                 ││ This will permanently   │
 │                                 ││ destroy your files.     │
 └─────────────────────────────────┘└─────────────────────────┘
```

ridinCLIgun splits your terminal in two: a **real shell** on the left, an **advisory pane** on the right. Type anything — it watches in real time and warns you before you hit Enter on something you'll regret.

Add an AI backend and it becomes a second pair of eyes: reviewing pipelines, explaining flags, catching mistakes — all without ever running a single command for you.

**You drive. It rides shotgun.**

## What it does

- **Instant local warnings** — offline regex catalog catches dangerous patterns before you hit Enter
- **AI command review** — ask Claude to review what you're about to run (opt-in, explicit trigger)
- **Real shell** — not a wrapper, not a sandbox. Full PTY with colors, tab completion, history
- **Secret mode** — one toggle to block anything from reaching the AI
- **Draggable split pane** — resize with mouse or keyboard
- **Copy/paste** — mouse-select text in either pane, clipboard integration


### Why this exists

ridinCLIgun is a first coding project, born from curiosity after many years far away from code. It's entirely vibe-coded with AI assistance — and that's the point: 
For now, this is a personal project for me to learn how things work and change in the new AI-driven world and to creatively bring my ideas to life. 
I also see the terminal as essential for learning the basics of working with LLMs and multi-agent systems—especially using OpenClaw as an example—so I can really dive into the subject. I think that communicating with the computer via the terminal is a barrier for many people who aren’t that tech-savvy but are curious. 
I want to reach those people with this product.

So:
The terminal is where the real learning happens: LLMs, multi-agent systems, tools like Claude Code — they all live here. But the command line is also where most people stop. It may feel hostile, unforgiving, one wrong keystroke away from disaster :-)

This project exists because I believe the terminal shouldn't be a gatekeeper. If you're curious enough to open one, you deserve a companion that helps you learn safely — not a tool that takes over.


## New to the terminal?

The command line is powerful — but unforgiving. There's no "undo" for most things, and a typo in the wrong place renders a command useless, can wipe files or break your system. That's exactly why ridinCLIgun exists.

Think of it as training wheels that never get in your way. Type commands like you normally would — if something looks risky, the advisory pane lights up and tells you *why* before you run it. With AI review enabled, you can ask "is this safe?" in plain English.

You'll learn faster because you see the consequences *before* they happen, not after.

## Quick start

```bash
git clone git@github.com:inference-garden/ridinCLIgun.git
cd ridinCLIgun
pip install -e ".[all]"
python -m ridincligun
```

### Want AI review?

```bash
echo "ANTHROPIC_API_KEY=your-key" >> ~/.config/ridincligun/.env
```

Then `Ctrl+G, A` inside the app to switch it on.

## Shortcuts

Everything goes through `Ctrl+G` as a leader key (vim-style, no timeout):

| Key | What it does |
|-----|-------------|
| `Ctrl+G, R` | Ask AI to review current command |
| `Ctrl+G, A` | Toggle AI on/off |
| `Ctrl+G, S` | Toggle Secret mode |
| `Ctrl+G, C` | Copy selected text |
| `Ctrl+G, V` | Paste |
| `Ctrl+G, X` | Restart shell |
| `Ctrl+G, H` | Show all shortcuts |
| `F6` / `F7` | Resize panes |
| `Ctrl+Q` | Quit |

## Status

**v0.2** — early release, macOS only, Python 3.12+. Works, has rough edges.

## Config

`~/.config/ridincligun/` — auto-created on first run:

- `config.toml` — UI preferences, provider settings
- `.env` — API keys (gitignored, stays local)

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/
```

## License

GPL-3.0-or-later — see [LICENSE](LICENSE)
