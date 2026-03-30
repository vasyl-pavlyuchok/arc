#!/usr/bin/env python3
"""
ARC Stats — Token savings report from output-trimmer activity.
Part of ARC (Adaptive Rule Context) — github.com/vasyl-pavlyuchok/arc

Usage:
    python3 ~/.claude/hooks/../tools/arc-stats.py
    python3 arc-stats.py --log /path/to/trim-stats.log
    python3 arc-stats.py --days 7
"""
import argparse
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

LOG_PATH = Path.home() / '.claude' / 'hooks' / 'trim-stats.log'
# Rough estimate: average 4 chars per token
CHARS_PER_LINE_AVG = 80
CHARS_PER_TOKEN = 4


def parse_log(log_path: Path, since: date | None = None) -> list[dict]:
    """Parse trim-stats.log entries."""
    entries = []
    if not log_path.exists():
        return entries

    # Format: 2026-03-30 | docker logs | 342 → 60 lines | cmd: docker logs foo
    pattern = re.compile(
        r'^(\d{4}-\d{2}-\d{2})\s*\|\s*([^|]+)\|\s*(\d+)\s*→\s*(\d+)\s*lines\s*\|\s*cmd:\s*(.*)$'
    )

    with open(log_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = pattern.match(line)
            if not m:
                continue
            entry_date = date.fromisoformat(m.group(1))
            if since and entry_date < since:
                continue
            entries.append({
                'date': entry_date,
                'command': m.group(2).strip(),
                'original': int(m.group(3)),
                'trimmed': int(m.group(4)),
                'saved': int(m.group(3)) - int(m.group(4)),
                'cmd_preview': m.group(5).strip(),
            })

    return entries


def estimate_tokens(lines: int) -> int:
    return (lines * CHARS_PER_LINE_AVG) // CHARS_PER_TOKEN


def print_report(entries: list[dict], period_label: str):
    if not entries:
        print(f"\nNo trim data for {period_label}.")
        print(f"Log path: {LOG_PATH}")
        print("Trimming activates after the first verbose command (>1000 chars output).")
        return

    total_original = sum(e['original'] for e in entries)
    total_trimmed = sum(e['trimmed'] for e in entries)
    total_saved = sum(e['saved'] for e in entries)
    pct = (total_saved / total_original * 100) if total_original > 0 else 0

    tokens_saved = estimate_tokens(total_saved)
    tokens_original = estimate_tokens(total_original)

    print(f"\n{'='*50}")
    print(f"  ARC Output Trimmer — {period_label}")
    print(f"{'='*50}")
    print(f"  Activations:    {len(entries):>8,}")
    print(f"  Lines original: {total_original:>8,}")
    print(f"  Lines kept:     {total_trimmed:>8,}")
    print(f"  Lines saved:    {total_saved:>8,}  ({pct:.1f}%)")
    print(f"  Tokens saved ~: {tokens_saved:>8,}  (of ~{tokens_original:,})")
    print()

    # Per-command breakdown
    by_cmd: dict[str, dict] = defaultdict(lambda: {'count': 0, 'saved': 0, 'original': 0})
    for e in entries:
        by_cmd[e['command']]['count'] += 1
        by_cmd[e['command']]['saved'] += e['saved']
        by_cmd[e['command']]['original'] += e['original']

    print(f"  {'Command':<16} {'Hits':>5}  {'Lines saved':>11}  {'Reduction':>9}")
    print(f"  {'-'*16} {'-'*5}  {'-'*11}  {'-'*9}")
    for cmd, stats in sorted(by_cmd.items(), key=lambda x: -x[1]['saved']):
        cmd_pct = (stats['saved'] / stats['original'] * 100) if stats['original'] > 0 else 0
        print(f"  {cmd:<16} {stats['count']:>5}  {stats['saved']:>11,}  {cmd_pct:>8.1f}%")

    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description='ARC output-trimmer statistics')
    parser.add_argument('--log', type=Path, default=LOG_PATH, help='Path to trim-stats.log')
    parser.add_argument('--days', type=int, default=None, help='Only show last N days (default: all time)')
    parser.add_argument('--week', action='store_true', help='Show last 7 days')
    parser.add_argument('--month', action='store_true', help='Show last 30 days')
    args = parser.parse_args()

    since = None
    label = 'all time'

    if args.week:
        since = date.today() - timedelta(days=7)
        label = 'last 7 days'
    elif args.month:
        since = date.today() - timedelta(days=30)
        label = 'last 30 days'
    elif args.days:
        since = date.today() - timedelta(days=args.days)
        label = f'last {args.days} days'

    entries = parse_log(args.log, since)
    print_report(entries, label)


if __name__ == '__main__':
    main()
