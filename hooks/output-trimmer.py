#!/usr/bin/env python3
"""
Output Trimmer - PostToolUse hook for Claude Code
Reduces token waste from verbose bash command outputs.
Tailored for: Next.js dev, Docker, git, npm, Python, Rust workflows.
"""
import json
import sys
import re


# Limits per command type (lines)
LIMITS = {
    "ls":           40,
    "find":         60,
    "git diff":    120,
    "git log":      40,
    "git status":   60,
    "docker logs":  60,   # keep tail (most recent)
    "docker ps":    30,
    "docker images": 30,
    "npm":          30,   # keep tail (summary)
    "yarn":         30,
    "pnpm":         30,   # keep tail (summary)
    "pip":          40,   # keep tail (installed packages summary)
    "cargo":        50,   # keep tail (build/test summary)
    "pytest":       60,   # keep tail (test results summary)
    "jest":         60,   # keep tail (test results summary)
    "wc":          100,
}

GENERIC_LIMIT = 300  # fallback for any unrecognized long output


def extract_final_command(command: str) -> str:
    """Extract the last command in a chain (split on && and |)."""
    parts = re.split(r'&&|\|', command)
    return parts[-1].strip()


def classify(command: str) -> tuple[str | None, bool]:
    """Returns (key, keep_tail). keep_tail=True means keep last N lines instead of first N."""
    cmd = extract_final_command(command)
    if re.match(r'ls\b', cmd):
        return "ls", False
    if re.match(r'find\b', cmd):
        return "find", False
    if "git diff" in cmd:
        return "git diff", False
    if "git log" in cmd:
        return "git log", False
    if "git status" in cmd:
        return "git status", False
    if re.match(r'docker\s+logs\b', cmd):
        return "docker logs", True  # keep recent lines
    if re.match(r'docker\s+ps\b', cmd):
        return "docker ps", False
    if re.match(r'docker\s+images\b', cmd):
        return "docker images", False
    if re.match(r'npm\b', cmd):
        return "npm", True  # keep summary at end
    if re.match(r'yarn\b', cmd):
        return "yarn", True
    if re.match(r'pnpm\b', cmd):
        return "pnpm", True   # keep summary at end
    if re.match(r'pip\b', cmd):
        return "pip", True    # keep installed packages at end
    if re.match(r'cargo\b', cmd):
        return "cargo", True  # keep build/test summary at end
    if re.match(r'pytest\b', cmd):
        return "pytest", True # keep test results at end
    if re.match(r'jest\b', cmd):
        return "jest", True   # keep test results at end
    if re.match(r'wc\b', cmd):
        return "wc", False
    return None, False


def trim(output: str, limit: int, keep_tail: bool) -> str:
    lines = output.rstrip().split("\n")
    if len(lines) <= limit:
        return output

    omitted = len(lines) - limit
    note = f"[⚡ {omitted} lines trimmed by output-trimmer]"

    if keep_tail:
        return note + "\n" + "\n".join(lines[-limit:])
    else:
        return "\n".join(lines[:limit]) + "\n" + note


def main():
    try:
        input_data = json.load(sys.stdin)

        if input_data.get("hook_event_name") != "PostToolUse":
            return
        if input_data.get("tool_name") != "Bash":
            return

        command = input_data.get("tool_input", {}).get("command", "")
        output = input_data.get("tool_response", {}).get("output", "")

        if not output or len(output) < 1000:
            return  # Short outputs: not worth trimming

        key, keep_tail = classify(command)
        limit = LIMITS.get(key, GENERIC_LIMIT) if key else GENERIC_LIMIT

        trimmed = trim(output, limit, keep_tail)

        if trimmed != output:
            # Log trim event for pattern analysis
            try:
                import datetime
                log_path = "/root/.claude/hooks/trim-stats.log"
                original_lines = len(output.split("\n"))
                trimmed_lines = len(trimmed.split("\n"))
                with open(log_path, "a") as f:
                    f.write(f"{datetime.date.today()} | {key or 'generic'} | {original_lines} → {trimmed_lines} lines | cmd: {command[:80]}\n")
            except Exception:
                pass

            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "output": trimmed
                }
            }))

    except Exception:
        pass  # Never break the workflow


if __name__ == "__main__":
    main()
