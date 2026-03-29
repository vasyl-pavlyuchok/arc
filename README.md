# ARC — Adaptive Rule Context

> Smart rule injection for Claude Code. Load only what matters.

🇪🇸 [Versión en español disponible al final del documento](#en-español)

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

### El problema

Cada vez que envías un mensaje en Claude Code, tu `CLAUDE.md` (o cualquier archivo de reglas estático) carga **todo** — sin importar lo que estés haciendo en ese momento.

Con 30, 50, 100 reglas acumuladas entre Docker, flujos de trabajo, proyectos activos y comportamiento general, estás quemando miles de tokens por mensaje en contexto que no es relevante para la tarea actual.

### La inspiración

Anthropic ya resolvió este problema — en el propio sistema de **skills** de Claude Code.

Las skills siempre son visibles como `nombre + descripción corta`. La definición completa solo se carga cuando la skill se invoca. Tienes consciencia sin overhead.

ARC aplica exactamente el mismo patrón a tus reglas:

| Sistema de skills | ARC |
|---|---|
| `nombre + descripción corta` siempre visible | Variante `_SHORT` siempre inyectada |
| Definición completa al invocar | Dominio completo al detectar keyword |
| Tú eliges la skill por nombre | Claude hace match por palabras clave en tu prompt |

No es una invención nueva — viene directamente del diseño de Anthropic. ARC solo extiende esa lógica a tus propias reglas.

### La solución

Las reglas se organizan en **dominios** y solo se cargan cuando aparecen palabras clave relevantes en tu prompt.

| Mensaje | Qué se carga |
|---|---|
| "¿cómo funciona este componente?" | Solo GLOBAL (resúmenes cortos) |
| "arregla el problema con docker" | GLOBAL + DOCKER (reglas completas) |
| "configura el webhook de n8n" | GLOBAL + tu dominio de workflows |
| Trabajando en `/projects/miweb/` | GLOBAL + MIWEB (detección por ruta) |

**85–90% menos overhead de contexto** — mismo comportamiento inteligente, mucho menos coste.

### Cómo funciona

ARC es un hook `UserPromptSubmit` de Claude Code. Se ejecuta antes de cada mensaje e inyecta solo lo relevante.

```
Vasyl envía mensaje
       ↓
arc-hook.py lee ~/.arc/manifest
       ↓
¿Qué dominios hacen match con las keywords de este prompt?
       ↓
Carga: GLOBAL (variantes SHORT) + dominios con match (reglas completas)
       ↓
Inyecta como additionalContext → Claude solo ve las reglas pertinentes
```

### Protocolo de evolución

ARC está diseñado para crecer contigo. Cuando Claude detecta un patrón repetible, propone una regla:

> *"Patrón ARC detectado — dominio DOCKER, regla propuesta: 'Siempre revisar los logs del contenedor antes de asumir que un servicio está caído.' ¿La registramos?"*

Las reglas solo se añaden cuando tú confirmas. Las que resultan obsoletas se eliminan. **ARC se mantiene lean o se convierte en ruido.**

### Instalación

```bash
git clone https://github.com/vasyl-pavlyuchok/arc.git
cd arc
chmod +x install.sh
./install.sh
```

Luego configura los hooks en `~/.claude/settings.json` (ver sección completa arriba en inglés).

Las contribuciones en español son bienvenidas.
