#!/usr/bin/env python3
"""
ARC CLI — Inspect and debug your ARC configuration.
Part of ARC (Adaptive Rule Context) — github.com/vasyl-pavlyuchok/arc

Usage:
    arc status               Show active config summary
    arc test "your prompt"   Simulate which domains would match
    arc domains              List all domains and their recall keywords
    arc sessions             List recent sessions
    arc stats                Show output-trimmer token savings
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ARC_DIR = Path.home() / '.arc'
SESSIONS_DIR = ARC_DIR / 'sessions'
LOG_PATH = Path.home() / '.claude' / 'hooks' / 'trim-stats.log'


# ─── Manifest parsing (minimal, no arc-hook dependency) ─────────────────────

def parse_manifest(manifest_path: Path) -> dict:
    """Parse ~/.arc/manifest into a dict of domain configs."""
    domains = {}
    devmode = False
    global_exclude = []

    if not manifest_path.exists():
        return {'domains': domains, 'devmode': devmode, 'global_exclude': global_exclude}

    with open(manifest_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip()

            if key == 'DEVMODE':
                devmode = value.lower() == 'true'
                continue
            if key == 'GLOBAL_EXCLUDE':
                global_exclude = [k.strip() for k in value.split(',') if k.strip()]
                continue

            if key.endswith('_STATE'):
                domain = key[:-6]
                domains.setdefault(domain, {})['state'] = value.lower() == 'active'
            elif key.endswith('_ALWAYS_ON'):
                domain = key[:-10]
                domains.setdefault(domain, {})['always_on'] = value.lower() == 'true'
            elif key.endswith('_RECALL'):
                domain = key[:-7]
                domains.setdefault(domain, {})['recall'] = value
                domains.setdefault(domain, {})['recall_list'] = [
                    k.strip().lower() for k in value.split(',') if k.strip()
                ]
            elif key.endswith('_EXCLUDE'):
                domain = key[:-8]
                domains.setdefault(domain, {})['exclude_list'] = [
                    k.strip().lower() for k in value.split(',') if k.strip()
                ]
            elif key.endswith('_PATH'):
                domain = key[:-5]
                domains.setdefault(domain, {})['path'] = value

    return {'domains': domains, 'devmode': devmode, 'global_exclude': global_exclude}


def match_prompt(prompt: str, domains: dict) -> dict[str, list[str]]:
    """Return {domain: [matched_keywords]} for a given prompt."""
    prompt_lower = prompt.lower()
    matched = {}
    for domain, config in domains.items():
        if not config.get('state', False) or config.get('always_on', False):
            continue
        for keyword in config.get('recall_list', []):
            pattern = r'(?<!\w)' + re.escape(keyword) + r'(?!\w)'
            if re.search(pattern, prompt_lower):
                matched.setdefault(domain, []).append(keyword)
    return matched


# ─── Commands ────────────────────────────────────────────────────────────────

def cmd_status(args):
    """Show active ARC configuration summary."""
    if not ARC_DIR.exists():
        print(f"✗ ARC not installed — ~/.arc not found")
        sys.exit(1)

    manifest_path = ARC_DIR / 'manifest'
    config = parse_manifest(manifest_path)
    domains = config['domains']

    print(f"\n  ARC — {ARC_DIR}")
    print(f"  {'─'*44}")
    print(f"  DEVMODE:   {'on' if config['devmode'] else 'off'}")

    # Sessions
    session_count = len(list(SESSIONS_DIR.glob('*.json'))) if SESSIONS_DIR.exists() else 0
    print(f"  Sessions:  {session_count} active")

    # Domains
    always_on = [d for d, c in domains.items() if c.get('state') and c.get('always_on')]
    on_demand = [d for d, c in domains.items() if c.get('state') and not c.get('always_on')]
    inactive = [d for d, c in domains.items() if not c.get('state')]

    print(f"\n  {'Domain':<20} {'Status':<12} {'Keywords'}")
    print(f"  {'─'*20} {'─'*12} {'─'*30}")

    for d in sorted(domains):
        c = domains[d]
        if not c.get('state'):
            status = 'inactive'
        elif c.get('always_on'):
            status = 'always-on'
        else:
            status = 'on-demand'
        recall = c.get('recall', '—')
        if len(recall) > 40:
            recall = recall[:37] + '...'
        print(f"  {d:<20} {status:<12} {recall}")

    print()


def cmd_test(args):
    """Simulate which domains match a given prompt."""
    if not args.prompt:
        print("Usage: arc test \"your prompt here\"")
        sys.exit(1)

    prompt = args.prompt
    manifest_path = ARC_DIR / 'manifest'
    config = parse_manifest(manifest_path)
    domains = config['domains']

    matched = match_prompt(prompt, domains)
    always_on = [d for d, c in domains.items() if c.get('state') and c.get('always_on')]

    print(f"\n  Prompt: \"{prompt}\"")
    print(f"  {'─'*50}")

    if always_on:
        print(f"\n  Always loaded ({len(always_on)}):")
        for d in always_on:
            domain_file = ARC_DIR / d.lower()
            rules = count_rules(domain_file)
            print(f"    ✓ {d}  ({rules} rules)")

    if matched:
        print(f"\n  Matched by keyword ({len(matched)}):")
        for domain, keywords in sorted(matched.items()):
            domain_file = ARC_DIR / domain.lower()
            rules = count_rules(domain_file)
            print(f"    ✓ {domain}  — matched: {', '.join(keywords)}  ({rules} rules)")
    else:
        print(f"\n  No on-demand domains matched.")

    not_matched = [
        d for d, c in domains.items()
        if c.get('state') and not c.get('always_on') and d not in matched
    ]
    if not_matched:
        print(f"\n  Not matched ({len(not_matched)}): {', '.join(sorted(not_matched))}")

    print()


def count_rules(domain_file: Path) -> int:
    """Count non-SHORT rules in a domain file."""
    if not domain_file.exists():
        return 0
    count = 0
    with open(domain_file) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key = line.split('=', 1)[0].strip()
                if not key.endswith('_SHORT'):
                    count += 1
    return count


def cmd_domains(args):
    """List all domains with recall keywords."""
    manifest_path = ARC_DIR / 'manifest'
    config = parse_manifest(manifest_path)

    print()
    for domain, c in sorted(config['domains'].items()):
        state_marker = '✓' if c.get('state') else '✗'
        tag = ' [always-on]' if c.get('always_on') else ''
        domain_file = ARC_DIR / domain.lower()
        rules = count_rules(domain_file)
        print(f"  {state_marker} {domain}{tag}  ({rules} rules)")
        if c.get('recall'):
            keywords = [k.strip() for k in c['recall'].split(',')]
            for i in range(0, len(keywords), 6):
                chunk = ', '.join(keywords[i:i+6])
                prefix = '    keywords: ' if i == 0 else '               '
                print(f"{prefix}{chunk}")
        if c.get('path'):
            print(f"    path:     {c['path']}")
        print()


def cmd_sessions(args):
    """List recent sessions."""
    if not SESSIONS_DIR.exists():
        print("\n  No sessions found.\n")
        return

    sessions = []
    for f in SESSIONS_DIR.glob('*.json'):
        try:
            with open(f) as fp:
                data = json.load(fp)
            sessions.append(data)
        except Exception:
            continue

    sessions.sort(key=lambda x: x.get('last_activity', ''), reverse=True)
    limit = args.limit if hasattr(args, 'limit') and args.limit else 10
    sessions = sessions[:limit]

    if not sessions:
        print("\n  No sessions found.\n")
        return

    print(f"\n  {'Title':<40} {'Prompts':>7}  {'Last activity'}")
    print(f"  {'─'*40} {'─'*7}  {'─'*20}")
    for s in sessions:
        title = s.get('title') or s.get('label') or s.get('uuid', '')[:8]
        if len(title) > 38:
            title = title[:35] + '...'
        prompts = s.get('prompt_count', 0)
        last = s.get('last_activity', '')[:16].replace('T', ' ')
        print(f"  {title:<40} {prompts:>7}  {last}")
    print()


def cmd_stats(args):
    """Show output-trimmer token savings (delegates to arc-stats.py)."""
    stats_script = Path(__file__).parent / 'arc-stats.py'
    if not stats_script.exists():
        print(f"\n  arc-stats.py not found at {stats_script}\n")
        sys.exit(1)
    import runpy
    sys.argv = ['arc-stats.py']
    if hasattr(args, 'week') and args.week:
        sys.argv += ['--week']
    elif hasattr(args, 'month') and args.month:
        sys.argv += ['--month']
    runpy.run_path(str(stats_script), run_name='__main__')


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog='arc',
        description='ARC CLI — inspect and debug your ARC configuration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  status            Show active config summary
  test "prompt"     Simulate which domains would match
  domains           List all domains and recall keywords
  sessions          List recent sessions
  stats             Show output-trimmer token savings
        """
    )

    sub = parser.add_subparsers(dest='command')

    sub.add_parser('status', help='Show active config summary')

    p_test = sub.add_parser('test', help='Simulate which domains match a prompt')
    p_test.add_argument('prompt', nargs='?', help='Prompt to test')

    sub.add_parser('domains', help='List all domains and recall keywords')

    p_sessions = sub.add_parser('sessions', help='List recent sessions')
    p_sessions.add_argument('--limit', type=int, default=10, help='Max sessions to show')

    p_stats = sub.add_parser('stats', help='Show output-trimmer savings')
    p_stats.add_argument('--week', action='store_true')
    p_stats.add_argument('--month', action='store_true')

    args = parser.parse_args()

    if args.command == 'status':
        cmd_status(args)
    elif args.command == 'test':
        cmd_test(args)
    elif args.command == 'domains':
        cmd_domains(args)
    elif args.command == 'sessions':
        cmd_sessions(args)
    elif args.command == 'stats':
        cmd_stats(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
