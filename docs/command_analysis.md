# Command Analysis

What ridinCLIgun checks, when, and how deep it goes.

## Always-on local advisory
Runs locally on every input change, no provider needed:

| Component | Trigger | Output |
|-----------|---------|--------|
| **Secret detection** | every input change, **runs first** | flags secret-bearing input; interrupts/gates AI review until the user confirms |
| Risk pattern catalog | every keystroke | matched warnings from the command-family catalog |
| tldr command catalog | every keystroke | description + examples |
| Typo detector | unknown command name | nearest-command suggestion |

## Layered review
| Layer | Trigger | Network | What happens |
|-------|---------|---------|--------------|
| Local advisory | every keystroke | no | the always-on components above |
| **Layer 2 — AI review** | user presses `F2` (AI enabled, provider configured) | yes | the redacted command is reviewed by the provider; secrets/sensitive paths are redacted, structure preserved |
| **Layer 3 — deep analysis** | automatic after Layer 2 when there's fetchable remote-execute evidence | yes | the remote script is fetched locally, then its content is analysed (never executed) |

## How deep it goes — the investigation-depth router
After `F2` a review always runs.
The app chooses **Fast vs Deep** automatically and decides whether Layer 3 runs, based on the value of deeper investigation — see `investigation_depth_router.md`. The user picks only the **provider**; the active model (Fast or Deep) is always shown.


## Layer 3 fetch — limits and safety
| Property | Value |
|----------|-------|
| Allowed schemes | **`https` only** — `http` and all others rejected before any network call |
| SSRF guard | every resolved IP checked; private/loopback/link-local/reserved blocked |
| Redirects | re-validated per hop (scheme + IP) before following |
| Pre-fetch gate | blocked while Secret Mode would expose secrets |
| Max fetch | 1 MB · timeout 15 s · **execution: never** (read-only) |

## What it does not cover
No shell AST / semantic parsing. No analysis across separate commands or sessions. No deep analysis
for plain downloads that aren't executed in the same command.
