# ARC — Adaptive Rule Context

> Smart rule injection for Claude Code. Load only what matters, when it matters.

Built by [Vasyl Pavlyuchok](https://github.com/vasyl-pavlyuchok) & [Claude](https://claude.ai) (Anthropic) — human direction, AI implementation, shared authorship.

🇪🇸 [Versión en español → README.es.md](README.es.md)

---

## The Problem

Every time you send a message in Claude Code, your `CLAUDE.md` (or any static rule file) loads **everything** — regardless of what you're actually doing.

With 30, 50, 100 rules across Docker, workflows, projects, and behavior — you're burning thousands of tokens per message on overhead that's irrelevant most of the time.

This is the **CARL problem**: rules accumulate, everything loads on every message, and your context window slowly fills with rules you don't need right now.

There's a second, subtler problem that follows from the first: **context rot**. As a session grows longer, the context window fills up and Claude silently discards the oldest content to make room. It doesn't warn you. It doesn't stop working. It just starts forgetting — decisions made earlier, constraints you established, context that seemed stable. The longer the session, the worse it gets: Claude contradicts itself, repeats questions, ignores rules it was following an hour ago.

ARC attacks context rot on two fronts: by keeping rule overhead low (so useful context lasts longer), and by tracking how full the session is and adjusting behavior before things go wrong.

## The Insight

Anthropic already solved this problem — in Claude Code's own **skills system**.

Skills are always visible as a `name + short description`. The full definition only loads when the skill is invoked. You get awareness without overhead.

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

ARC is a set of Claude Code hooks. The main one runs before every message and injects only what's relevant.

```
User sends message
       ↓
arc-hook.py reads ~/.arc/manifest
       ↓
Checks: which domains match keywords in this prompt?
Checks: which domains match file paths in recent tool calls?
       ↓
Loads: GLOBAL (SHORT variants) + matched domains (full rules)
       ↓
Injects as additionalContext → Claude sees only relevant rules
```

### Hooks Overview

| Hook | Event | What it does |
|---|---|---|
| `arc-hook.py` | UserPromptSubmit | Main injector — keyword + path matching, domain loading, context brackets |
| `arc-suggest.py` | Stop | Analyzes session — suggests new keywords for unmatched prompts |
| `arc-semantic.py` | UserPromptSubmit | Semantic fallback — matches by meaning when keywords miss (opt-in) |
| `output-trimmer.py` | PostToolUse (Bash) | Trims verbose command output to prevent context bloat |
| `secret-scanner.py` | PreToolUse (Bash) | Blocks git commits containing hardcoded API keys and secrets |

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
# ~/.arc/docker
DOCKER_RULE_1_SHORT=Reverse proxy as single entry point. Never expose ports directly.
DOCKER_RULE_1=Use a reverse proxy (Traefik, Nginx, or Caddy) as the single entry point
for all traffic on ports 80 and 443. Container ports must never be exposed directly
to the internet — not even temporarily. Reasons: automatic SSL termination, centralized
routing and access logs, ability to add middleware (auth, rate-limiting, headers) in one
place, and clean rollback without touching DNS. Common mistake to avoid: mapping host
ports in docker-compose (e.g. "8080:80") on production — this bypasses the proxy and
creates uncontrolled entry points that are easy to forget and hard to audit. If you need
to test locally, use the proxy network; never use host port mapping as a shortcut.
```

- `_SHORT` variant: injected on every prompt (compact, ≤15 words)
- Full variant: injected only when domain is keyword-matched — rationale, examples, and edge cases included

### Context Brackets

Every Claude Code session has a finite context window — a fixed amount of space for everything: your messages, Claude's responses, tool outputs, and injected rules. As a session progresses, this space fills up. When it runs out, Claude starts losing the oldest content silently. It doesn't warn you. It doesn't stop. It just forgets.

ARC reads the token count from the session's JSONL log and calculates how much space remains. Based on that percentage, it places the session in one of four **brackets** — and injects a different set of behavioral rules for each one.

| Bracket | Remaining | What ARC tells Claude to do |
|---|---|---|
| FRESH | 60–100% | Work normally. Lean injection, minimal overhead. |
| MODERATE | 40–60% | Reinforce key decisions. Summarize state before starting large tasks. |
| DEPLETED | 25–40% | Checkpoint everything. Prepare handoff notes in case the session ends. |
| CRITICAL | <25% | Warn the user. Recommend opening a fresh session before continuing. |

**This is ARC's direct counter to context rot.** Without bracket-aware rules, Claude behaves the same whether the session is 5 minutes old or 3 hours deep — even while silently dropping context. Brackets make the session's health visible and change Claude's behavior accordingly, so degradation is caught before you lose work or get inconsistent outputs without knowing why.

### Star Commands

Prefix your prompt with `*commandname` to load a specific set of rules for that mode, regardless of keywords:

```
*dev    fix the login form validation
*review check this PR before merging
```

Star commands map to dedicated rule sets defined in your manifest. Useful when you want to force a specific context — code review standards, deployment checklist, debugging protocol — without relying on keyword detection.

### Path Detection

ARC inspects file paths from recent tool calls to load domains automatically — without any keywords in your prompt.

```ini
# manifest
MYAPP_PATH=/absolute/path/to/myapp
```

If Claude reads or edits a file under that path, the domain loads automatically.

---

## Installation

```bash
git clone https://github.com/vasyl-pavlyuchok/arc.git
cd arc
chmod +x install.sh
./install.sh
```

The installer automatically merges the required hooks into your `~/.claude/settings.json`. No manual JSON editing needed. It's idempotent — safe to run multiple times.

Restart Claude Code and ARC is active.

> **Not sure how to install it?** Just paste this repo's URL into Claude Code and it will guide you through the entire setup.

---

## CLI Tools

ARC ships with a command-line interface for debugging and introspection.

### `arc test` — debug matching before you commit

```bash
arc test "I want to configure an n8n workflow with docker"
```

```
Prompt: "I want to configure an n8n workflow with docker"
Always loaded (2): ✓ GLOBAL (33 rules), ✓ CONTEXT (19 rules)
Matched by keyword (2):
  ✓ DOCKER  — matched: docker  (12 rules)
  ✓ N8N     — matched: n8n, workflow  (7 rules)
Not matched (5): COMMANDS, DASHBOARD_UI, ESTETIA, SERVIDOR, VASYLPAVLYUCHOK
```

This is the most useful tool when building new domains — see exactly what would load before testing in a real session.

### Other commands

```bash
arc status           # active config — devmode, domains, state
arc domains          # full list with keywords and rule counts
arc sessions         # recent sessions with title, prompt count, last activity
arc stats            # token savings report (delegates to arc-stats.py)
arc stats --week     # last 7 days
arc stats --month    # last 30 days
```

No external dependencies — works immediately after installation.

### `arc-stats` — measure real savings

`arc-stats.py` processes the output-trimmer log and reports actual numbers:

```
Period: last 7 days
Activations: 47
Lines trimmed: 1,823 → 312 (83% reduction)
Estimated tokens saved: ~3,800
Top commands: git diff (18), docker logs (12), npm install (9)
```

Turns the "85–90% estimated" into a real number for your specific usage.

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

## Advanced: Semantic Matching

By default ARC uses keyword matching — fast and zero-overhead. For cases where the exact keyword doesn't appear in the prompt, you can enable semantic matching as a fallback.

```ini
# ~/.arc/manifest
SEMANTIC_MATCHING=true
SEMANTIC_THRESHOLD=0.55
```

When enabled:
- Only activates when keyword matching returns 0 domain matches
- Uses `sentence-transformers` with `all-MiniLM-L6-v2` (~80MB, runs offline)
- Embeddings are cached at `~/.arc/embeddings.cache.pkl`
- Adds ~1–2s latency on fallback cases only, 0ms otherwise

**Example**: "fix the service that won't start" → matches DOCKER even without the word "docker".

> Requires `pip install sentence-transformers`. Disabled by default — keyword matching handles most cases.

---

## ARC Evolution Protocol

ARC is designed to grow with you. When Claude detects a repeatable pattern, it proposes a rule:

> *"ARC pattern detected — domain DOCKER, proposed rule: 'Always check container logs before assuming a service is down.' Register it?"*

Rules only get added when you confirm. Rules that prove wrong get removed. **ARC stays lean or it becomes noise.**

A rule earns its place only if it's:
1. **Repeatable** — applies across future sessions
2. **Actionable** — changes concrete behavior
3. **Stable** — won't need to change in weeks

### arc-suggest — automatic evolution

At the end of each session, `arc-suggest.py` analyzes your prompts and surfaces candidates for new domains or keywords:

```
💡 ARC: Unmatched prompts this session suggest new keywords:
   supabase  (appeared in 3 unmatched prompts)
   migration (appeared in 2 unmatched prompts)
```

Non-blocking — it never interrupts your workflow. Just a nudge when something worth capturing shows up.

---

## Requirements

- Claude Code (any version with hooks support)
- Python 3.10+
- macOS, Linux, or WSL
- `sentence-transformers` only if enabling semantic matching

---

## Philosophy

Static rule files are a good start. But they don't scale.

ARC treats rules like code: organized by domain, loaded on demand, evolved over time, and pruned when stale. The result is a Claude Code setup that gets smarter with use — without ever bloating your context window. Rules that don't earn their place get removed. The system stays lean because lean is the point.

---

## License

MIT — built by [Vasyl Pavlyuchok](https://github.com/vasyl-pavlyuchok) & Claude.
