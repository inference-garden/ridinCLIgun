# Investigation-Depth Router

## Principle
Local-first. AI runs **only on the user's explicit trigger** (F2). Deeper, costlier analysis runs
**only when it adds real evidence or value** — at minimal privacy/cost footprint. The question is
not "how dangerous?" but **"how much does deeper investigation add here?"**

Key distinction: **danger ≠ investigation value.**
- `git reset --hard` — dangerous, but fully knowable locally; deeper analysis adds ~nothing.
- `bash <(curl …)` — fetchable remote content the user can't see; deeper analysis earns its cost.

## Provider selection (what the user chooses)
The user picks a **provider they trust** — that's the only model choice. The app maps the provider
to a Fast and a Deep model and **always shows which model is talking**.

| Provider | Fast | Deep |
|----------|------|------|
| Anthropic | Claude Haiku 4.5 | Claude Sonnet 4.6 |
| OpenAI | GPT-5.4 mini | GPT-5.4 |
| Mistral | Mistral Small | Mistral Medium 3.5 |

Config stores only the provider. No per-model menu, no pinned-model migration. The model set is visible, never silently substituted.

## CommandFacts — one local pass
A single local analysis of the typed command produces the facts the router needs (reused by the
Layer 3 trigger and prompt categorisation too, so there's one source of truth, no drift):

| Fact | Meaning |
|------|---------|
| `severity` | highest risk from the local catalog (safe / caution / warning / danger) |
| `boundary_score` | count of trust-boundary crossings: sudo/root, write `/etc`, write `/dev`, network fetch, public exposure, secret handling |
| `complexity_score` | obfuscation/composition: `$()`/backticks, `eval`, `source`, heredoc, `&&` `;` `\|\|`, ≥2 pipes, `xargs`/`find -exec` |
| `evidence_gain` | can deeper analysis fetch new evidence? e.g. a fetchable remote-script URL — yes/no |
| `category` | prompt category for composite commands — resolved here once, **not** first-match-wins |

Raw signals like pipe-count and command length are **weak contributors inside `complexity_score` only** — never standalone triggers (too imprecise).

## Routing
Two outputs from one decision. **Floor = Fast AI:** after F2 a review always happens (never
no-API); the router only decides the depth.

| Output | Rule |
|--------|------|
| **Fetch evidence → Layer 3 deep analysis** (uses Deep model) | `evidence_gain = yes` **and** (`severity ≥ warning` **or** `boundary ≥ 2` **or** `complexity ≥ 1`) |
| **Layer 2 review model** | **Deep** if it fetched (above) **or** `severity ≥ warning` **or** `boundary ≥ 2` **or** `complexity ≥ 2`; otherwise **Fast** |

So: trivial command → Fast review, no fetch. Risky/complex local command → Deep review, no fetch.
Fetchable remote-execute → Deep review **+** Layer 3 fetch & analysis. The active tier and model
are shown in the UI every time.

## Fetch or No-fetch...
1. **Model and fetch are separate.** A risky/complex *local* command (no fetchable evidence) still
   gets the **Deep model** for its Layer 2 review; the fetch additionally requires `evidence_gain`.
2. **Thresholds confirmed:** fetch gate `boundary ≥ 2` / `complexity ≥ 1`; Deep-model rule
   `boundary ≥ 2` / `complexity ≥ 2` (as in the routing table above). Tunable later if real-world
   use shows over/under-triggering.

## Prerequisite (sequencing)
Layer 3 must run on its dedicated **deep-analysis system prompt** (locale-aware), not the generic
category prompt, **before** Deep triggering is broadened.

## Out of scope
No shell AST/semantic parsing. The router uses cheap, local, deterministic signals only.

## As built (v0.4.7, 2026-06-14)
Implemented exactly as above — thresholds, provider table, and the model-vs-fetch separation all
match the shipped code. Where it landed:
- `advisory/command_facts.py` — `CommandFacts` + the two deterministic scorers (`score_boundary`,
  `score_complexity`) + `build_command_facts` (injects `resolve_category` + the L3 trigger so the
  advisory layer stays provider-free). Corpus-pinned in `tests/test_command_facts.py`.
- `advisory/router.py` — pure `route(facts) -> RoutingDecision{layer2_tier, fetch}`; emits an
  abstract tier (`"fast"`/`"deep"`), not a model id. Thresholds pinned in `tests/test_router.py`
  (incl. the Fast-floor invariant).
- `provider/registry.py` — provider → (Fast, Deep) ids; `provider/manager.py` holds a Fast + a Deep
  adapter and runs each review on the routed tier; `app.py` wires facts → route → L2 on the tier →
  L3 on the **Deep** model explicitly, and shows the active **"tier · model"** every review
  (i18n `router.active`). Config is provider-only; a vestigial `model=` is silently ignored.
