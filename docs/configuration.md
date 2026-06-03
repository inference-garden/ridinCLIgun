# Configuration

This document covers config files, runtime settings, persistence, and current provider/model presets. For privacy impact of local history, see `security.md`.

## Config directory

ridinCLIgun uses:

`~/.config/ridincligun/`

On first run it creates:

- `config.toml`
- `.env`

If an existing `.env` is readable by group or others, ridinCLIgun tightens it to `0600`.

## Files

| File | Purpose |
|------|---------|
| `~/.config/ridincligun/config.toml` | app settings |
| `~/.config/ridincligun/.env` | API keys |

## Effective settings

### `[general]`

| Key | Current meaning | Runtime default |
|-----|-----------------|-----------------|
| `ai_enabled_default` | start with AI on or off | `false` |
| `language` | UI / AI language (`en`, `de`, `fr`) | `""` = auto-detect from system locale |
| `review_mode` | prompt tone (`default`, `explorer`) | `default` |
| `shell` | override shell binary | `""` = use `$SHELL`, else `/bin/zsh` fallback |

### `[provider]`

| Key | Current meaning | Current value on fresh template |
|-----|-----------------|---------------------------------|
| `kind` | selected provider kind | `anthropic` |
| `model` | selected model id | `claude-sonnet-4-6` |
| `timeout_seconds` | provider request timeout | `10.0` |
| `max_tokens` | response token cap | `1024` |

Supported provider kinds in the current runtime:

- `anthropic`
- `openai`
- `mistral`

If `kind` is unknown, runtime falls back to Anthropic.

### `[privacy]`

| Key | Current meaning | Runtime default |
|-----|-----------------|-----------------|
| `show_redaction_preview` | show original vs. redacted command before send | `true` |
| `clipboard_safety` | warn before pasting secret-looking text | `true` |

### `[ui]`

| Key | Current meaning | Runtime default |
|-----|-----------------|-----------------|
| `split_ratio` | shell pane : advisory pane width ratio | `[3, 2]` |

## What is configurable in-app

| Setting | Where it persists | Notes |
|---------|-------------------|-------|
| language | `config.toml` | cycles through available locales |
| `ai_enabled_default` | `config.toml` | startup AI state |
| provider / model | `config.toml` | selected via settings or model selector |
| `review_mode` | `config.toml` | `default` or `explorer` |
| `show_redaction_preview` | `config.toml` | privacy toggle |
| `clipboard_safety` | `config.toml` | privacy toggle |
| API keys | `.env` | settings writes matching provider key |
| `split_ratio` | `config.toml` | saved on app shutdown |

## Current provider/model presets in the v0.4 worktree

These are the presets currently shown by the in-app selector:

| Label | Provider | Model id |
|-------|----------|----------|
| Mistral Fast Review | `mistral` | `mistral-small-2603` |
| Mistral Deep Review | `mistral` | `mistral-medium-3-5` |
| Claude Fast Review | `anthropic` | `claude-haiku-4-5` |
| Claude Deep Review | `anthropic` | `claude-sonnet-4-6` |
| OpenAI Fast Review | `openai` | `gpt-5.4-mini` |
| OpenAI Deep Review | `openai` | `gpt-5.4` |

Manual model ids are also possible by editing `config.toml`.

## API keys

Supported variables: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `MISTRAL_API_KEY`

Read order:

1. matching key in `~/.config/ridincligun/.env`
2. matching key from the process environment

Runtime notes:

- keys are loaded into app memory, not into the embedded shell environment
- switching provider/model re-reads the relevant key from `.env` and then `os.environ`
- adding a key in settings writes it to `.env`; restart or provider/model re-selection is the reliable way to make the active provider pick it up

## Layout persistence

- `F9` grows the advisory pane
- `F10` grows the shell pane
- the current `split_ratio` is saved on app shutdown
