# Changelog

All notable changes to ridinCLIgun are documented here. Dates are ISO 8601.
This project follows [Semantic Versioning](https://semver.org/) loosely while in the
v0.x line. The advisory layer is always local-first; an AI backend is optional.

## [0.4.7] — 2026-06-20

### Changed
- **Automatic model selection via an investigation-depth router.** You now pick only a
  provider you trust; ridinCLIgun chooses a **Fast** or **Deep** model per command from
  cheap, local, deterministic signals and always shows which model is answering. Trivial
  commands get a fast review; risky or complex local commands get the deep model; a
  remote-execute script is fetched and deeply analysed only when that adds real insight.
  The six-option model menu is replaced by a three-provider selector that shows each
  provider's Fast and Deep models.
- **Configuration is now provider-only.** A leftover `model` value in an existing
  `config.toml` is read and silently ignored — no migration needed.
- **Deep analysis (Layer 3) now runs on the provider's Deep model explicitly**, and the
  active tier and model are recorded in the review history.

### Added
- A single local "command facts" pass — severity, trust-boundary and complexity signals,
  fetchable-evidence detection, and prompt category — is the one source of truth behind
  the router, the Layer 3 trigger, and prompt categorisation, removing drift between them.
  Behaviour is pinned by corpus and threshold tests.
- Documentation: a new **Investigation-Depth Router** page, and refreshed **Configuration**,
  **Command Analysis**, and **Prompt Category System** docs (the last now lists the verbatim
  prompts sent to the provider).

### Fixed
- A malformed `config.toml` now fails with one clear message (file and line) and a
  non-zero exit instead of a raw traceback — failing closed, never silently falling back
  to defaults.

## [0.4.6] — 2026-06-13

### Added
- **Faster install via prebuilt bottles.** `brew install ridincligun` now pours a
  prebuilt binary in seconds instead of compiling a Rust/LLVM toolchain. Installing
  from source remains supported as a fallback.
- **`exit ride`** quits ridinCLIgun cleanly from the shell prompt — an exact,
  case-insensitive match that never triggers as part of a larger command line.
- **Scroll indicator in the advisory pane** when content overflows, so it is clear
  there is more to read.

### Changed
- **Offline help responds to the command variant you type.** Typing a subcommand
  (e.g. `git commit`) now shows that subcommand's page; the examples matching the
  flags and arguments you have typed are surfaced to the top and highlighted, and a
  short per-flag note is shown. Everything stays local and synchronous, with
  localized descriptions falling back to English.

### Security
- Hardened the command-pattern and secret-detection regexes against catastrophic
  backtracking (ReDoS), with a standing screening test across all patterns.
- The bundled tldr catalog is now integrity-checked at build/package time against a
  pinned manifest.
- The deep-analysis fetch connects to the validated, pinned IP (closing a
  DNS-rebinding gap), and the dependency audit in CI now also covers the optional
  AI SDKs.

## [0.4.5] — 2026-06-04

### Added
- **Homebrew install.** ridinCLIgun can now be installed on macOS via a Homebrew tap:
  `brew tap inference-garden/ridincligun && brew install ridincligun`. Installing from
  source with `pip` remains supported.
- `ridincligun --version` prints the version and exits (no terminal UI required).

## [0.4.4] — 2026-06-03

### Fixed
- **AI review works again on Anthropic, OpenAI, and Mistral.** When an optional
  provider SDK was missing from the environment, the app reported every failure as a
  generic "check connection", hiding the real cause. Missing-SDK and missing-key
  situations now show a clear, actionable message; genuine API/network errors stay
  sanitized so keys and endpoints never leak.
- OpenAI requests now use `max_completion_tokens`, which current GPT-5 models require
  (the old parameter caused them to fail).
- Provider rate limits (HTTP 429) now say "wait and retry" instead of looking like a
  connection failure.
- Deep-analysis output now respects the selected interface language (German/French),
  matching the normal review — previously it could answer in English.
- A model context-size lookup that wrongly rejected large scripts.

### Added
- **Copy/paste via the leader key:** `Ctrl+G, C` (copy selection) and `Ctrl+G, V`
  (paste). Pasted text is scanned for secrets and must be confirmed before it reaches
  the shell; terminal control sequences are stripped so a crafted clipboard cannot
  inject keystrokes.

### Security
- The remote-script "deep analysis" fetch is now safe by default: HTTPS only; the
  resolved address must be public (loopback, private, link-local, and cloud metadata
  endpoints are refused); every redirect is re-validated; and toggling Secret Mode
  cancels the fetch itself rather than only the later send.

### Changed
- Default model presets refreshed (OpenAI `gpt-5.4-mini` / `gpt-5.4`; Anthropic default
  `claude-sonnet-4-6`).

## [0.4.3] — 2026-05-28

### Changed
- Documentation overhaul: trilingual `CONTRIBUTING.md` (EN/DE/FR), rewritten README
  with screenshots, version resynced.

## [0.4.2] — 2026-05-26

### Security
- Test-suite hardening: load-bearing security controls (secret-mode block, suggestion
  insertion never executing, sanitization at the review boundary, deep-analysis fetch
  path, history file permissions) are now defended by focused regression tests.

## [0.4.1] — 2026-05-26

### Changed
- Keyboard shortcut redesign: frequent actions on function keys, `Ctrl+G` reserved as a
  leader for modal actions.
- Documentation overhaul; added a dependency lock file.

## [0.4.0] — 2026-04-14

### Added
- Offline `tldr` command catalog (thousands of commands).
- Interface localization (English, German, French) — including AI responses.
- Review history browser.
- Smarter AI: per-category prompts, explorer mode, and deep analysis of remote
  install scripts.
- Provider/model selection with persistence.

[0.4.7]: https://github.com/inference-garden/ridinCLIgun/releases/tag/v0.4.7
[0.4.6]: https://github.com/inference-garden/ridinCLIgun/releases/tag/v0.4.6
[0.4.5]: https://github.com/inference-garden/ridinCLIgun/releases/tag/v0.4.5
[0.4.4]: https://github.com/inference-garden/ridinCLIgun/releases/tag/v0.4.4
[0.4.3]: https://github.com/inference-garden/ridinCLIgun/releases/tag/v0.4.3
[0.4.2]: https://github.com/inference-garden/ridinCLIgun/releases/tag/v0.4.2
[0.4.1]: https://github.com/inference-garden/ridinCLIgun/releases/tag/v0.4.1
[0.4.0]: https://github.com/inference-garden/ridinCLIgun/releases/tag/v0.4.0
