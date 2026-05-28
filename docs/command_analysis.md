# Command Analysis

This document covers what ridinCLIgun checks, when it checks it, and what each layer covers. Data flow lives in `security.md`; prompt composition lives in `prompt_category_system.md`.

## Always-on local advisory

These components run locally and do not require a provider:

| Component | Trigger | Current source | Output |
|-----------|---------|----------------|--------|
| Risk pattern catalog | every keystroke | 17 command families / 31 regex patterns | matched warnings |
| tldr command catalog | every keystroke | bundled tldr-pages data | description + examples |
| Typo detector | when command name is unknown | tldr commands + catalog + PATH scan | nearest command suggestion |

The tldr bundle currently covers 6,615 commands.

## Layered review flow

| Layer | Trigger | Network | What happens |
|-------|---------|---------|--------------|
| Local advisory | every keystroke | no | regex warnings, tldr lookup, typo detection |
| Layer 2 AI review | user presses `F2` with AI enabled and provider configured | yes | current command is reviewed by the selected provider |
| Layer 3 deep analysis | automatically after Layer 2 if a remote-execute pattern matched | yes | URL is fetched locally, then script content is sent for analysis |

Layer 2 uses the matched warning families to resolve a prompt category before sending the command.

## Layer 3 trigger rules

Layer 3 currently activates for these command shapes:

| Pattern | Example |
|---------|---------|
| pipe to shell | `curl https://example.com/install.sh | bash` |
| pipe to shell via `wget` | `wget -qO- https://example.com/setup | sh` |
| download then execute same file | `curl -o script.sh https://example.com/s.sh && bash script.sh` |
| fallback URL + shell pipe | any command containing both an `http(s)://...` URL and `| bash`, `| sh`, `| zsh`, or `| dash` |

The explicit download-and-execute matcher also recognizes `source script.sh`.

## Layer 3 fetch and fit limits

| Limit | Current value | Effect |
|-------|---------------|--------|
| max fetch size | 1,048,576 bytes | content above 1 MB is cut locally |
| fetch timeout | 15 seconds | slow or hanging fetches abort |
| allowed schemes | `http`, `https` | other schemes are rejected |
| execution | never | content is read only |
| context fitting | model-dependent | fetched script may be truncated again before provider send |

## What the layers do not cover

- no shell AST or semantic shell parsing
- no analysis across separate commands or sessions
- no deep analysis for plain downloads that are not executed in the same command
- no deep analysis for heredocs, stdin-fed content, or shell builtins such as `source` unless matched by the download-and-execute regex
- no authenticated fetch flow for login-walled scripts
- no guarantee against novel credential formats or obfuscated shell tricks

