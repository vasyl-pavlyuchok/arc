#!/usr/bin/env python3
"""
ARC Suggest — Stop hook for Claude Code
Analyzes unmatched prompts at session end and suggests new domain keywords.
Part of ARC (Adaptive Rule Context) — github.com/vasyl-pavlyuchok/arc

Fires on the Stop event. Reads recent session history, finds prompts
that loaded 0 on-demand domains, extracts candidate keywords, and
prints suggestions to stderr if any are worth adding.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ARC_DIR = Path.home() / '.arc'
MIN_FREQUENCY = 2       # word must appear in N+ unmatched prompts to be suggested
MIN_WORD_LEN = 4        # ignore short words
MAX_PROMPTS_TO_SCAN = 20
SUGGESTION_THRESHOLD = 2  # min candidates before printing anything

# Words to ignore (common, non-domain-specific)
STOPWORDS = {
    'this', 'that', 'with', 'have', 'from', 'they', 'will', 'been', 'were',
    'what', 'when', 'where', 'which', 'would', 'could', 'should', 'make',
    'does', 'just', 'some', 'also', 'more', 'into', 'than', 'then', 'them',
    'your', 'like', 'want', 'need', 'here', 'there', 'about', 'after',
    'before', 'other', 'such', 'each', 'same', 'over', 'only', 'very',
    'bien', 'para', 'pero', 'como', 'todo', 'esto', 'eso', 'eso', 'esos',
    'está', 'este', 'esta', 'algo', 'quiero', 'hacer', 'puede', 'tiene',
    'porque', 'ahora', 'cuando', 'donde', 'cómo', 'qué', 'también',
    'claude', 'please', 'help', 'okay', 'sure', 'file', 'files', 'code',
    'using', 'used', 'that', 'from', 'with', 'update', 'check',
}


def parse_manifest_domains(arc_path: Path) -> dict:
    """Parse manifest to get active domains and their recall keywords."""
    domains = {}
    manifest_path = arc_path / 'manifest'
    if not manifest_path.exists():
        return domains

    with open(manifest_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            if key.endswith('_STATE'):
                domain = key[:-6]
                domains.setdefault(domain, {})['state'] = value.strip().lower() == 'active'
            elif key.endswith('_ALWAYS_ON'):
                domain = key[:-10]
                domains.setdefault(domain, {})['always_on'] = value.strip().lower() == 'true'
            elif key.endswith('_RECALL'):
                domain = key[:-7]
                domains.setdefault(domain, {})['keywords'] = set(
                    k.strip().lower() for k in value.split(',') if k.strip()
                )
    return domains


def all_known_keywords(domains: dict) -> set:
    """Collect all keywords across all domains."""
    known = set()
    for config in domains.values():
        known.update(config.get('keywords', set()))
    return known


def prompt_matches_any_domain(prompt: str, domains: dict) -> bool:
    """Check if prompt triggered at least one on-demand domain."""
    prompt_lower = prompt.lower()
    for config in domains.values():
        if not config.get('state') or config.get('always_on'):
            continue
        for kw in config.get('keywords', set()):
            pattern = r'(?<!\w)' + re.escape(kw) + r'(?!\w)'
            if re.search(pattern, prompt_lower):
                return True
    return False


def extract_candidate_words(text: str, known_keywords: set) -> list[str]:
    """Extract meaningful words from text, excluding known keywords and stopwords."""
    words = re.findall(r'\b[a-záéíóúüñA-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ0-9\-_]{3,}\b', text)
    candidates = []
    for w in words:
        w_lower = w.lower()
        if (
            w_lower not in STOPWORDS
            and w_lower not in known_keywords
            and len(w_lower) >= MIN_WORD_LEN
            and not w_lower.isdigit()
        ):
            candidates.append(w_lower)
    return candidates


def read_recent_prompts(session_id: str, cwd: str, limit: int) -> list[str]:
    """Read recent user prompts from session JSONL transcript."""
    if not session_id or not cwd:
        return []

    home = Path.home()
    search_path = Path(cwd)
    transcript_file = None

    for _ in range(10):
        project_dir = str(search_path).replace('/', '-').lstrip('-')
        candidate = home / '.claude' / 'projects' / f'-{project_dir}' / f'{session_id}.jsonl'
        if candidate.exists():
            transcript_file = candidate
            break
        if search_path.parent == search_path:
            break
        search_path = search_path.parent

    if not transcript_file:
        return []

    prompts = []
    try:
        with open(transcript_file) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get('type') == 'user':
                        content = entry.get('message', {}).get('content', '')
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get('type') == 'text':
                                    content = block.get('text', '')
                                    break
                        if content and isinstance(content, str) and len(content.strip()) > 10:
                            prompts.append(content.strip())
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return prompts[-limit:]  # last N prompts


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if input_data.get('hook_event_name') != 'Stop':
        sys.exit(0)

    if not ARC_DIR.exists():
        sys.exit(0)

    session_id = input_data.get('session_id', '') or input_data.get('sessionId', '')
    cwd = input_data.get('cwd', '')

    domains = parse_manifest_domains(ARC_DIR)
    if not domains:
        sys.exit(0)

    known_keywords = all_known_keywords(domains)
    prompts = read_recent_prompts(session_id, cwd, MAX_PROMPTS_TO_SCAN)

    if not prompts:
        sys.exit(0)

    # Collect words from prompts that matched 0 on-demand domains
    unmatched_words: Counter = Counter()
    unmatched_count = 0

    for prompt in prompts:
        if not prompt_matches_any_domain(prompt, domains):
            unmatched_count += 1
            words = extract_candidate_words(prompt, known_keywords)
            unmatched_words.update(words)

    if not unmatched_words or unmatched_count < 2:
        sys.exit(0)

    # Filter to words appearing in multiple unmatched prompts
    candidates = [
        (word, count) for word, count in unmatched_words.most_common(10)
        if count >= MIN_FREQUENCY
    ]

    if len(candidates) < SUGGESTION_THRESHOLD:
        sys.exit(0)

    print('', file=sys.stderr)
    print('💡 ARC: Unmatched prompts this session suggest new keywords:', file=sys.stderr)
    for word, count in candidates[:5]:
        print(f'   {word}  (appeared in {count} unmatched prompts)', file=sys.stderr)
    print('', file=sys.stderr)
    print('   To add: edit ~/.arc/manifest → add to relevant domain\'s _RECALL', file=sys.stderr)
    print('   Or run: arc domains  to review current keyword coverage', file=sys.stderr)
    print('', file=sys.stderr)


if __name__ == '__main__':
    main()
