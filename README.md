**"Riding Shotgun" for your CLI** — a split-terminal TUI with an AI companion.


# ridinCLIgun

> Your terminal copilot that watches, warns — and knows the commands.

```
 ┌─ Shell ─────────────────────────────┐┌─ Advisory ──────────────────────────┐
 │ $ git push --force                  ││ ⚠ WARNING                           │
 │                                     ││ Force-push rewrites remote history. │
 │                                     ││ Teammates' work may be lost.        │
 │                                     ││                                     │
 │                                     ││ git — the fast version control sys  │
 │                                     ││                                     │
 │                                     ││ ▸ safer alternative:                │
 │                                     ││   git push --force-with-lease       │
 │                                     ││ ▸ push current branch:              │
 │                                     ││   git push origin HEAD              │
 └─────────────────────────────────────┘└─────────────────────────────────────┘
```

ridinCLIgun splits your terminal in two: a **real shell** on the left, an **advisory pane** on the right. Type anything — it watches in real time, warns you before you hit Enter on something you'll regret, and shows you what the command actually does.

The advisory pane knows 6,600+ commands. It shows examples, explains flags, and catches typos — all offline, no API key needed.

Add an AI backend and it goes further: reviewing pipelines, catching edge cases, explaining options — in your language.

**You drive. It rides shotgun. And it knows the roads.**

## What it does

**Instant local analysis — no AI, no internet, no waiting:**
- **Risk warnings** — offline catalog catches dangerous patterns as you type
- **Command knowledge** — 6,600+ commands with descriptions and real usage examples
- **Typo detection** — "Did you mean `git`?" when you type `gti`
- **Real shell** — full PTY with colors, tab completion, history, scrollback

**With AI enabled (opt-in, explicit trigger):**
- **AI command review** — ask Claude, GPT, or Mistral to review what you're about to run
- **Deep script analysis** — fetches and analyzes remote scripts from `curl | bash` patterns
- **AI suggestions** — context-aware alternatives, inserted directly into the shell

**Privacy and safety controls:**
- **Secret mode** — one toggle to block anything from reaching the AI
- **Redaction preview** — see exactly what gets sent to the AI before it leaves your machine
- **Clipboard safety** — warns before pasting commands containing secrets

**Configuration:**
- **Multi-language** — full UI in English, German, or French; AI responds in your language
- **History browser** — browse, search, and learn from your past AI reviews
- **Settings menu** — configure everything from inside the app (`Ctrl+G, G`)
- **Provider switching** — Anthropic, OpenAI, Mistral; choice persists across restarts
- **Explorer mode** — gentler tone for beginners and kids
- **Onboarding** — first-run guidance, no docs needed


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

## Prerequisites

| Requirement | Detail |
|-------------|--------|
| **Python** | >= 3.12 |
| **OS** | macOS (Linux planned) |
| **Terminal** | Any terminal emulator (iTerm2, Terminal.app, Warp, etc.) |
| **Shell** | Any POSIX shell — uses your default (zsh, bash, sh) |

For AI-powered review you also need an API key from one of the supported providers.

## Quick start

```bash
git clone git@github.com:inference-garden/ridinCLIgun.git
cd ridinCLIgun
```

### Install options

ridinCLIgun is **provider-agnostic** — it works with multiple AI providers,
or with no AI at all. Choose what fits:

**a) All AI providers** — install everything, decide later which to use:

```bash
pip install -e ".[all]"
```

**b) Lightweight** — local warnings only, no AI, no extra downloads:

```bash
pip install -e "."
```

**c) Pick your provider** — install only what you need:

```bash
pip install -e ".[mistral]"     # c1 — Mistral (le Chat)
pip install -e ".[anthropic]"   # c2 — Anthropic (Claude)
pip install -e ".[openai]"      # c3 — OpenAI (GPT)
```

Then start the app:

```bash
python -m ridincligun
```

### Setting up AI review

Add your API key to the config file (created on first run):

```bash
# Mistral (https://console.mistral.ai/)
echo "MISTRAL_API_KEY=your-key" >> ~/.config/ridincligun/.env

# Anthropic (https://console.anthropic.com/)
echo "ANTHROPIC_API_KEY=your-key" >> ~/.config/ridincligun/.env

# OpenAI (https://platform.openai.com/)
echo "OPENAI_API_KEY=your-key" >> ~/.config/ridincligun/.env
```

Inside the app: `Ctrl+G, A` to toggle AI on, `Ctrl+G, M` to switch between models/providers.

Or enter keys from inside the app: `Ctrl+G, G` → navigate to a provider → Enter.

## Shortcuts

Everything goes through `Ctrl+G` as a leader key (vim-style, no timeout):

| Key | What it does |
|-----|-------------|
| `Ctrl+G, R` | Ask AI to review current command |
| `Ctrl+G, I` | Insert AI suggestion into shell |
| `Ctrl+G, A` | Toggle AI on/off |
| `Ctrl+G, M` | Switch AI model/provider |
| `Ctrl+G, K` | Open review history browser |
| `Ctrl+G, S` | Toggle Secret mode |
| `Ctrl+G, ?` | Show --help for current command |
| `Ctrl+G, C` | Copy selected text |
| `Ctrl+G, V` | Paste |
| `Ctrl+G, X` | Restart shell |
| `Ctrl+G, G` | Open settings |
| `Ctrl+G, H` | Show all shortcuts |
| `F6` / `F7` | Resize panes |
| `Ctrl+Q` | Quit |

## Status

**v0.4** — "This tool is genuinely useful." macOS, Python 3.12+.

## Config

`~/.config/ridincligun/` — auto-created on first run:

- `config.toml` — UI preferences, provider, language, split ratio
- `.env` — API keys (gitignored, stays local, 0600 permissions)

Language setting: `language = "de"` (or `"fr"`, `"en"`) in `[general]`. Leave empty for auto-detect from `$LANG`.

## Command catalog

The offline command knowledge comes from [tldr-pages](https://github.com/tldr-pages/tldr) (v2.3, MIT license) — a community-maintained database of practical command examples. 6,615 commands across common, Linux, and macOS platforms. German and French overlays included. Bundled as plain JSON — no network access at runtime.

## Documentation

| Document | What it covers |
|----------|---------------|
| [Command Analysis](docs/command_analysis.md) | How the 3-layer analysis system decides what to check |
| [Security Model](docs/security.md) | What is sent to the AI, security layers, known limits |
| [Roadmap](docs/roadmap.md) | Where the project is heading |

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v        # 377 tests
ruff check src/
```

## Keywords
terminal safety, CLI safety, shell safety, command review, dangerous commands, terminal copilot, split-terminal TUI, pipe inspection, command assistance, tldr, beginner-friendly terminal

## License

GPL-3.0-or-later — see [LICENSE](LICENSE)
