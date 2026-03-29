# ARC — Adaptive Rule Context

> Smart rule injection for Claude Code. Load only what matters.

---

## The Problem

Every time you send a message in Claude Code, your `CLAUDE.md` (or any static rule file) loads **everything** — regardless of what you're actually doing.

With 30+ rules across areas like Docker, workflows, project context, and behavior — you're burning thousands of tokens per message on overhead that's irrelevant most of the time.

This is the **CARL problem**: rules accumulate, everything loads on every message, and your context window slowly fills with rules you don't need right now.

## The Insight

Anthropic already solved this problem — in Claude Code's own **skills system**.

Skills are always visible as a `name + short description`. The full definition only loads when the skill is actually invoked. You get awareness without overhead.

ARC applies the exact same pattern to your rules:

| Skills system | ARC |
|---|---|
| `name + short description` always visible | `_SHORT variant` always injected |
| Full definition loads on invocation | Full domain loads on keyword match |
| You pick the skill by name | Claude matches by keyword in your prompt |

The design principle isn't new — it comes directly from how Anthropic built Claude Code. ARC just extends it to your own rules and workflows.

## The Solution

Rules are organized into **domains** and loaded only when relevant keywords appear in your prompt.

| Prompt | What loads |
|---|---|
| "how does this function work?" | GLOBAL only (short summaries) |
| "fix the docker network issue" | GLOBAL + DOCKER (full rules) |
| "set up the webhook endpoint" | GLOBAL + your workflow domain |
| Working in `/projects/myapp/` | GLOBAL + MYAPP (path-detected) |

**~85–90% reduction in rule injection overhead** — same intelligent behavior, fraction of the context cost.

---

## How It Works

ARC is a Claude Code `UserPromptSubmit` hook. It runs before every message and injects only what's relevant.

```
User sends message
       ↓
arc-hook.py reads ~/.arc/manifest
       ↓
Checks: which domains match keywords in this prompt?
       ↓
Loads: GLOBAL (SHORT variants) + matched domains (full rules)
       ↓
Injects as additionalContext → Claude sees only relevant rules
```

### Domain Structure

```
~/.arc/
├── manifest        # which domains exist and their keywords
├── global          # always loaded (SHORT variants only)
├── context         # context bracket rules (FRESH/MODERATE/DEPLETED)
├── docker          # loaded when: docker, container, compose...
├── myproject       # loaded when: keywords match OR path detected
└── sessions/       # per-session state (auto-managed)
```

### Rule Format

```ini
# domains/docker
DOCKER_RULE_1_SHORT=Reverse proxy as single entry point. Never expose ports directly.
DOCKER_RULE_1=Use a reverse proxy (Traefik, Nginx, Caddy) as the single entry point
on 80/443. Never expose container ports directly to the internet.
```

- `_SHORT` variant: injected on every prompt (compact, ≤15 words)
- Full variant: injected only when domain is keyword-matched

### Context Brackets

ARC tracks how much context window remains and adjusts behavior:

| Bracket | Remaining | Behavior |
|---|---|---|
| FRESH | 60-100% | Lean injection, minimal overhead |
| MODERATE | 40-60% | Reinforce key context, summarize before big tasks |
| DEPLETED | 25-40% | Checkpoint everything, prepare handoffs |
| CRITICAL | <25% | Warn and recommend fresh session |

---

## Installation

```bash
git clone https://github.com/vasyl-pavlyuchok/arc.git
cd arc
chmod +x install.sh
./install.sh
```

Then add the hooks to your `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/arc-hook.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/output-trimmer.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/secret-scanner.py"
          }
        ]
      }
    ]
  }
}
```

Restart Claude Code and ARC is active.

---

## Creating Your Own Domains

**1. Create the domain file** at `~/.arc/myproject`:

```ini
# ARC Domain: MYPROJECT
MYPROJECT_RULE_1_SHORT=Read CLAUDE.md before touching any file in this project.
MYPROJECT_RULE_1=Always read the project's CLAUDE.md before making changes. It contains
architecture decisions and constraints that aren't obvious from the code.

MYPROJECT_RULE_2_SHORT=Dev server: docker compose -f docker-compose.dev.yml up
MYPROJECT_RULE_2=To start development: docker compose -f docker-compose.dev.yml up
Production deploy: docker compose build && docker compose up -d
```

**2. Register it in `~/.arc/manifest`**:

```ini
MYPROJECT_STATE=active
MYPROJECT_ALWAYS_ON=false
MYPROJECT_RECALL=myproject, my-app, feature-x, deploy staging
MYPROJECT_PATH=/absolute/path/to/myproject   # optional: auto-load by file path
```

**3. That's it.** Next time you mention a recall keyword or work in that path, the domain loads automatically.

---

## ARC Evolution Protocol

ARC is designed to grow with you. When Claude detects a repeatable pattern, it proposes a rule:

> *"ARC pattern detected — domain DOCKER, proposed rule: 'Always check container logs before assuming a service is down.' Register it?"*

Rules only get added when you confirm. Rules that prove wrong get removed. **ARC stays lean or it becomes noise.**

A rule earns its place only if it's:
1. **Repeatable** — applies across future sessions
2. **Actionable** — changes concrete behavior
3. **Stable** — won't need to change in weeks

---

## Included Hooks

| Hook | Event | What it does |
|---|---|---|
| `arc-hook.py` | UserPromptSubmit | Main injector — keyword matching, domain loading, context brackets |
| `output-trimmer.py` | PostToolUse (Bash) | Trims verbose command output (git, docker, npm) to prevent context bloat |
| `secret-scanner.py` | PreToolUse (Bash) | Blocks git commits containing hardcoded API keys and secrets |
| `auto-commit.sh` | Stop | Auto-checkpoints WIP changes when Claude Code session ends |

---

## Requirements

- Claude Code (any version with hooks support)
- Python 3.10+
- macOS, Linux, or WSL

---

## Philosophy

Static rule files are a good start. But they don't scale.

ARC treats rules like code: organized by domain, loaded on demand, evolved over time, and pruned when stale. The result is a Claude Code setup that gets more effective with use — without ever bloating your context window.

The core idea isn't new. Look at how Claude Code skills work: a short description is always visible, the full definition only loads on invocation. That's lazy loading applied to AI context. ARC brings the same principle to your rules — the architecture was already there, we just connected the dots.

---

## License

MIT — built by [Vasyl Pavlyuchok](https://github.com/vasyl-pavlyuchok) & Claude.

---

## En Español

ARC es un sistema de inyección de reglas para Claude Code. En lugar de cargar todas las reglas en cada mensaje (lo que consume tokens innecesariamente), ARC organiza las reglas en **dominios** y solo las carga cuando detecta palabras clave relevantes en tu mensaje.

**Resultado**: 85-90% menos overhead de contexto, mismo comportamiento inteligente.

Instalación y documentación completa arriba (inglés). Las contribuciones en español son bienvenidas.
