# ridinCLIgun v0.2

This document is a standalone specification for ridinCLIgun.
It is written so another coding agent can start cold, understand the product intent, and choose its own implementation approach.

## 1. What does it do?

ridinCLIgun is a terminal companion with two panes:

- a real shell on the left
- an advisory assistant on the right

The shell is real and must stay usable like a normal shell.
The advisory assistant may:

- explain commands
- warn about risky commands
- review commands before execution
- suggest safer alternatives

The advisory assistant must never:

- execute commands
- press Enter for the user
- confirm prompts on behalf of the user
- take autonomous action inside the shell

The core purpose of the project is:

**help the user work in the terminal more safely and confidently without taking control away from them**

The intended user experience is:

- shell-first
- calm
- trustworthy
- useful even offline
- explicit rather than magical

The product should feel like a careful companion, not like an autonomous agent.

### Core workflows

The product should currently focus on only two primary workflows.

#### A. Local-only workflow

- user types a command
- local advisory logic reacts immediately if needed
- user decides whether to run it
- user executes manually with `Enter` or aborts with `Ctrl+C`

This workflow must remain useful with no network and no provider.

#### B. Explicit AI review workflow

- user types a command
- user explicitly asks for review
- local advisory appears immediately
- if AI is enabled and allowed, background AI review is added
- user decides whether to run or abort

AI review must be explicit.
It should not trigger automatically on every command.

### Product values

The project should optimize for:

- safety
- clarity
- user control
- simplicity
- publishability

The project should avoid:

- over-complex state systems
- noisy UI
- too many modes
- anything that makes the shell feel fake

## 2. Tech stack

Current implementation uses:

- Python 3
- Textual for the terminal UI
- a PTY-backed shell process
- local advisory logic in Python
- JSON/flat files for command and warning data
- pytest for tests
- ruff for linting

Provider-backed review exists through an adapter boundary.
The app currently supports a local/offline advisory layer and an optional provider-backed AI layer.

The project should continue to prefer:

- simple files
- explicit modules
- local logs
- data-driven patterns

The project should avoid introducing a database unless there is a very strong need.

## 3. Type of project

ridinCLIgun is:

- a terminal user interface app
- a local shell companion
- a safety and advisory tool

ridinCLIgun is not:

- a shell replacement
- an autonomous coding agent
- a general chat app
- a web-first product

Its identity should remain:

**a shell assistant that advises but never acts**

## 4. Any existing specs or ideas

The following ideas are already part of the product intent and should be preserved.

### A. The shell is primary

The shell is the main thing.
The right pane exists to help the user make better decisions, not to compete with the shell.

### B. AI must be optional

There must be a clear on/off concept for AI-backed review.

When AI is off:

- the shell still works
- local warnings still work
- the app remains useful

### C. Secret Mode matters

There must be a simple way to protect sensitive current input from being sent to an external provider.

Secret Mode should:

- be clearly visible
- block provider review for protected current input
- keep the shell usable
- favor privacy over convenience

### D. Local warnings are essential

The local warning layer is not a fallback luxury.
It is part of the core product.

It should catch important risky command families such as:

- recursive deletion
- piping remote content into a shell
- destructive disk writes
- dangerous permission changes
- similar high-risk command families

### E. Keep the workflow simple

The project recently moved toward a simpler model.
That direction should continue.

The user should be able to answer two questions at any moment:

1. What mode am I in?
2. What happens if I press Enter right now?

If the UI or logic makes those answers unclear, the design is too complicated.

### F. Publish a working version before re-architecting

The current architecture is not a perfect native terminal experience.
That is acceptable for now.

The project should first ship a functioning, stable, simplified version.
Only later, if needed, should it consider switching to a different terminal-widget architecture.

Future migration should remain possible, but should not complicate the current code unnecessarily.

## 5. Further relevant items

### 5.1 Current intended interaction model

The visible user-facing phases should stay very small:

- Typing
- Review loading
- Review ready
- Shell unavailable

User-facing modifiers should also stay simple:

- AI on/off
- Secret on/off

The system should avoid too many abstract privacy modes and internal states becoming visible in the UI.

### 5.2 Command safety data

The project should keep a machine-readable command catalog.

That catalog should:

- classify commands or command families
- contain both safe/common and dangerous examples
- support local warning generation
- be easy to extend over time

A separate human-readable test list is also useful for manual testing.

The command catalog should be treated as long-term project infrastructure, not as throwaway prototype data.

### 5.3 Reliability expectations

The shell must remain usable even when:

- the provider is unavailable
- the provider returns poor output
- the network fails
- the AI is disabled

If provider review fails, the app should degrade gracefully and rely on local advisory logic.

### 5.4 UX expectations

The interface should feel:

- calm
- readable
- not cluttered
- not overly technical

Warnings should be visually clear.
Status information should be useful but not noisy.
The shell pane should not feel secondary.

### 5.5 Current major known limitation

Provider-backed review is still less reliable for risky commands than for harmless commands.

That means:

- harmless commands may get a proper AI note
- risky commands may still need a local fallback note

This is currently acceptable only as an intermediate state.
Improving reliable AI review for risky commands is an important stabilization task.

### 5.6 What success looks like for v0.2

A good v0.2 should achieve this:

- user can work in a real shell
- local warnings work reliably
- AI review is explicit and understandable
- Secret Mode is trustworthy
- the UI feels calm and coherent
- the app is safe enough and stable enough to publish privately or publicly as an early version

### 5.7 Guidance for another coding agent

If you are another coding agent working on this project, optimize for:

- simplification before feature growth
- stability before novelty
- clean boundaries between shell, UI, provider, and safety logic
- preserving user control at all times

Do not assume the best next move is adding features.
The best next move is often:

- removing complexity
- clarifying workflows
- improving reliability
- making the product easier to understand

The spirit of ridinCLIgun is:

**a respectful, safety-minded shell companion that helps the user think before they run**
