# Roadmap

Next work only. Updated as steps complete.

---

## Current: Step 1 ✅
**Project scaffold + working shell**
- Two-pane Textual app with PTY-backed shell
- Advisory pane (placeholder), status bar
- Basic entry point

## Next: Step 2
**Shortcuts + divider + config**
- Ctrl+G leader key state machine
- Pane focus (Ctrl+1/2), divider resize (F6/F7)
- Config loading from ~/.config/ridincligun/

## Then: Step 3
**Local advisory engine**
- Command catalog (JSON, 20+ patterns)
- Local warning engine (pattern matching)
- Input parser (extract command from PTY buffer)
- Warnings rendered as colored blocks

## Then: Step 4
**AI review integration**
- Anthropic adapter
- Explicit review (Ctrl+G,R)
- AI on/off toggle, Secret Mode
- Graceful degradation on failure

## Then: Step 5
**Polish + publish**
- Help overlay, debug display, shell restart
- Copy/paste (Cmd+C/V with fallbacks)
- Full test suite, README, publish as package

## General direction
- Additional providers (OpenAI, Mistral)
- Model selection menu + credential management
- Linux/Windows support
- Homebrew
