# Command Analysis — Decision Matrix

How ridinCLIgun decides what to check and when.

---

## Three layers of analysis

| Layer | Name | Speed | Trigger | What happens |
|-------|------|-------|---------|-------------|
| 1 | **Local warning** | Instant | Every keystroke | Regex patterns match against a catalog of 31 known-dangerous command families. No network, no AI. |
| 2 | **AI structure review** | ~2-5s | User presses `Ctrl+G, R` | Command is sent to the AI for risk classification. Only privacy-sensitive values (secrets, credential paths) are redacted — full command structure is preserved so the AI can give accurate assessments. |
| 3 | **Deep script analysis** | ~5-15s | Automatic after Layer 2 when a remote-execute pattern is detected | The remote script is fetched, then sent to the AI for content analysis. |

## When does Layer 3 trigger?

Layer 3 activates automatically after a Layer 2 review when the command matches one of these patterns:

| Pattern | Example |
|---------|---------|
| Pipe to shell | `curl https://example.com/install.sh \| bash` |
| Pipe to shell (wget) | `wget -qO- https://example.com/setup \| sh` |
| Download then execute | `curl -o script.sh https://example.com/s.sh && bash script.sh` |
| URL + shell pipe | Any command containing both a URL and `\| bash/sh/zsh` |

## What Layer 3 reports

The AI analyzes the actual script content and reports:
- **What the script does** — installs, modifies, deletes, downloads
- **Network calls** — does it phone home, download more code?
- **Privilege escalation** — does it use `sudo`, modify system files?
- **Persistence** — does it install services, cron jobs, shell hooks?
- **Obfuscation** — encoded payloads, eval chains, minified code
- **Overall risk** — safe / caution / warning / danger

## Safety limits

| Limit | Value | Reason |
|-------|-------|--------|
| Max script size | 64 KB | Prevent memory abuse |
| Fetch timeout | 5 seconds | Prevent hanging on slow/malicious servers |
| Protocols | HTTP, HTTPS only | No file://, ftp://, or exotic schemes |
| Execution | Never | Content is only read and sent to AI for analysis |

## What is NOT checked

- Scripts loaded via `source`, `.`, or shell builtins
- Commands that download but don't immediately execute (`curl -O` alone)
- Scripts behind authentication (login-walled URLs)
- Multi-step attack chains across separate commands
- Content that arrives via stdin, clipboard, or heredoc

This matrix is best-effort. It makes dangerous patterns visible — it does not guarantee safety.
