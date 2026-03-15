# ridinCLIgun Shortcut Specification for macOS

This document describes the desired shortcut model for ridinCLIgun on macOS.

It is a target-state design document.
It describes how shortcuts should feel once the app is properly streamlined.

The guiding rule is:

**ridinCLIgun should respect normal macOS terminal behavior and should not steal standard shell-editing shortcuts unless there is a very strong reason.**

## 1. Design goals

The shortcut model should be:

- natural for macOS users
- respectful of terminal-native behavior
- easy to learn
- low-conflict
- calm and minimal

The shell must remain the primary interaction surface.
App shortcuts should not constantly compete with normal shell editing.

## 2. Core shortcut philosophy

There are three shortcut groups.

### A. Terminal-native shortcuts

These belong to the shell and terminal experience.
ridinCLIgun should not override them if possible.

Examples:

- `Tab`
- `Shift+Tab`
- `Enter`
- arrow keys
- `Home`
- `End`
- `Backspace`
- `Delete`
- `Ctrl+C`
- `Ctrl+D`
- `Ctrl+L`
- `Ctrl+R`
- `Ctrl+S`
- `Ctrl+Z`
- `Ctrl+A`
- `Ctrl+E`
- `Ctrl+U`
- `Ctrl+W`

These should continue to behave like normal shell-editing and terminal controls.

### B. macOS-native app shortcuts

These should feel like a normal macOS app where possible.

Desired:

- `Cmd+C` copy current selection
- `Cmd+V` paste plain text into the shell prompt without executing
- `Cmd+Q` quit app

These should be primary shortcuts when technically possible.

### C. App-specific shortcuts

These are ridinCLIgun-specific actions.
They should be kept small in number and avoid conflicts with terminal-native keys.

Where needed, they should be grouped behind a leader key.

## 3. Primary shortcut model

### 3.1 Direct shortcuts

These should work directly without a leader.

#### macOS-native direct shortcuts

- `Cmd+C` copy current selection from the focused pane
- `Cmd+V` paste plain text into the shell prompt
- `Cmd+Q` quit the app

#### Focus and layout

- `Ctrl+1` focus shell pane
- `Ctrl+2` focus help/agent pane
- `F6` shrink divider
- `F7` grow divider
- `Esc` close temporary overlay or cancel command mode

`F6` and `F7` should stay because they are useful and do not conflict badly with shell behavior.

### 3.2 Leader-key actions

Use one leader key for app-specific actions that should not interfere with terminal-native input.

Recommended leader:

- `Ctrl+G`

This keeps app actions explicit and avoids taking over common shell keys.

Desired leader map:

- `Ctrl+G`, then `R` = review current command
- `Ctrl+G`, then `H` = show help / shortcuts
- `Ctrl+G`, then `X` = restart shell
- `Ctrl+G`, then `D` = show latest provider debug capture
- `Ctrl+G`, then `A` = toggle AI on/off
- `Ctrl+G`, then `S` = toggle Secret Mode
- `Ctrl+G`, then `C` = copy current selection if `Cmd+C` is unavailable
- `Ctrl+G`, then `V` = paste into shell if `Cmd+V` is unavailable
- `Ctrl+G`, then `Q` = quit if `Cmd+Q` is unavailable

Leader-key actions are a good fallback when host-terminal behavior prevents macOS-native shortcuts from reaching the app.

## 4. Shortcut rules by function

### 4.1 Shell input and execution

- typing should go to the shell
- `Enter` should execute in the shell only
- ridinCLIgun must never bind a shortcut that causes AI-driven execution

### 4.2 Review

- command review must be explicit
- recommended shortcut: `Ctrl+G`, then `R`
- review should never replace `Enter`

### 4.3 AI toggle

- there must be a simple explicit AI on/off shortcut
- recommended shortcut: `Ctrl+G`, then `A`

This should be distinct from emergency or kill semantics.
It is a normal user-facing mode switch, not just a failure control.

### 4.4 Secret Mode

- Secret Mode should be easy to toggle
- recommended shortcut: `Ctrl+G`, then `S`

### 4.5 Copy and paste

Desired behavior:

- copy copies only the current selection
- paste inserts plain text into the shell prompt
- paste must not execute automatically

If there is no selection, copy should do nothing or show a small calm notice.
It should never default to copying an entire pane.

### 4.6 Help

- there should be a visible in-app shortcut help view
- recommended shortcut: `Ctrl+G`, then `H`

The help should remain visible until explicitly dismissed or replaced by the next clear user action.

## 5. What must not be stolen from the shell

These shortcuts should remain shell-owned:

- `Tab` for completion
- `Ctrl+C` for interrupt
- `Ctrl+D` for EOF / shell exit behavior
- `Ctrl+L` for clear screen
- `Ctrl+R` for shell history search
- `Ctrl+A` / `Ctrl+E` for line start/end
- `Ctrl+U` / `Ctrl+W` for line editing
- `Ctrl+Z` for job control
- arrows for cursor movement and history

If ridinCLIgun takes these over, the shell will feel fake and frustrating.

## 6. Current technical reality vs desired future state

The desired shortcut model is macOS-native.
However, current technical reality may prevent some keys from reaching ridinCLIgun because it runs inside another terminal app.

That means:

- `Cmd+C` and `Cmd+V` may be intercepted by the host terminal
- right-click and context menu behavior may belong to the host terminal
- mouse and selection behavior may be constrained by the current architecture

For that reason, fallback leader-based shortcuts are still useful.

## 7. Recommended implementation priorities

To keep the shortcut system simple and publishable:

1. Preserve all important shell-native keys.
2. Keep `F6` and `F7` for divider resizing.
3. Implement `Cmd+C`, `Cmd+V`, and `Cmd+Q` where technically possible.
4. Keep `Ctrl+G` as the app leader for non-terminal actions.
5. Keep the number of app-specific shortcuts small.

## 8. What success looks like

A good macOS shortcut model for ridinCLIgun should feel like this:

- the shell behaves like a shell
- macOS copy/paste/quit feel natural
- app-specific actions are easy to access but do not interfere with typing
- the user does not have to remember too many custom keys

The final feeling should be:

**mostly terminal-native, lightly app-augmented, and never in the user’s way**
