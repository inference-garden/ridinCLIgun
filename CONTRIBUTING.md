# Contributing to ridinCLIgun

> Thank you for considering a contribution.
I feel really honoured :-)
This document explains how to get involved.

## Current status

ridinCLIgun is maintained by a single developer. 
Contributions are welcome, but response times may vary. 
Please be patient.

## How to help

### Report bugs

Open a [GitHub Issue](https://github.com/inference-garden/ridinCLIgun/issues). A good bug report includes:

- **OS and Python version** (e.g., macOS 15.4, Python 3.13)
- **Shell** (zsh, bash) and terminal emulator (Terminal.app, iTerm2, etc.)
- **Steps to reproduce** — what you typed, what happened
- **Expected behavior** — what should have happened
- **Prompt customization** — do you use Starship, Oh My Zsh, Powerlevel10k? (known layout interactions exist)

### Suggest features

Open an issue with the label `enhancement`. Check the [public roadmap](docs/roadmap.md) first — your idea might already be planned.

### Contribute code

1. **Fork** the repository
2. **Create a branch** from `master` (e.g., `fix/secret-detector-edge-case`)
3. **Make your changes** — keep them focused, one concern per PR
4. **Run the test suite**: `pytest` (all tests must pass)
5. **Run linting**: `ruff check`
6. **Open a Pull Request** against `master`

### What we look for in code review

In order of priority:

1. **Security** — never leak secrets, never bypass the 5-layer security model
2. **Privacy** — local-first, no data leaves without explicit user consent
3. **The core principle** — AI advises, never acts. The user stays in control.
4. **Tests** — new features need tests, bug fixes need regression tests
5. **Minimal changes** — small, focused PRs are easier to review and merge

### What to avoid

- Do **not** add new dependencies without opening a discussion first
- Do **not** modify security controls (secret detector, sanitizer, AI blocking) without prior agreement
- Do **not** include secrets, API keys, or credentials in code, tests, or commit messages

## Development setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/ridinCLIgun.git
cd ridinCLIgun

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check
```

**Requirements:**
- Python 3.12+
- A real terminal with PTY support (won't work in Jupyter or similar)
- macOS (Linux support is planned)

## Architecture overview

ridinCLIgun is a split-terminal TUI built with [Textual](https://textual.textualize.io/) and [pyte](https://github.com/selectel/pyte). Key modules:

| Area | What it does |
|---|---|
| `advisory/` | Local pattern matching, risk engine, secret detection |
| `provider/` | AI adapters (Anthropic, OpenAI, Mistral), prompt sanitization |
| `ui/` | Shell pane, advisory pane, settings screen, status bar |
| `shell/` | PTY subprocess, command extraction |
| `shortcuts/` | Leader-key bindings (Ctrl+G prefix) |

See `docs/` in the repo for more detail.

## Licensing

ridinCLIgun is licensed under **GPL-3.0-or-later**.

By submitting a pull request, you agree that your contribution is licensed under the same terms. You retain copyright over your contribution.

> **Note:** The project may adopt a Contributor License Agreement (CLA) in the future to preserve licensing flexibility. If this becomes relevant, contributors will be notified and asked to sign before their contributions are merged.

## Playground Rules

Be decent to each other. Respect the humans (and the AIs). Stay courious.
That's it.

Longer version:
This is a self-aware playground.
- Be kind. We were all beginners once. Some of us still are.
- Be patient. This project is maintained by one human and several AIs
  who occasionally hallucinate.
- Have fun. This started as a curiosity project and that energy is sacred.

## Questions?

Open an issue or start a [Discussion](https://github.com/inference-garden/ridinCLIgun/discussions) on GitHub.

---

*This project is built with curiosity, AI assistance, and care. Welcome aboard.*
