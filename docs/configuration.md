# Model configuration

## You choose a provider, not a model
Pick the **provider you trust**. The app handles the rest — it uses a Fast model for quick reviews
and a Deep model for heavier analysis, and **always shows which model is answering** as a
**`tier · model`** label on every review (e.g. `Deep · claude-sonnet-4-6`).

| Provider | Fast review | Deep review |
|----------|-------------|-------------|
| Anthropic | Claude Haiku 4.5 | Claude Sonnet 4.6 |
| OpenAI | GPT-5.4 mini | GPT-5.4 |
| Mistral | Mistral Small | Mistral Medium 3.5 |

When you open the provider menu you can already see the two models that provider would use. The app never silently swaps a model — the one in use is visible in the UI.

## Where to set it
- In **Settings** (`Ctrl+G, G`) → Provider, or via the leader provider selector (`Ctrl+G, M`).
- In `config.toml`:
  ```toml
  [provider]
  kind = "anthropic"   # "anthropic" | "openai" | "mistral"
  timeout_seconds = 10.0
  max_tokens = 1024
  ```
  That's it — no model id to pick or maintain. Fast/Deep selection is automatic (see
  `investigation_depth_router.md`). A leftover `model = "…"` line from an older config is read and
  **silently ignored** (no migration). A malformed `config.toml` fails with one clear message
  (file + line) and exit 1 — it is never silently replaced by defaults.

## API keys
Keys live in `~/.config/ridincligun/.env` (owner-only), one per provider, loaded into app memory and passed only to that provider's adapter — never injected into the shell environment.
