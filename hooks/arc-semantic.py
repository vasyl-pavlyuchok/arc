#!/usr/bin/env python3
"""
ARC Semantic — Optional semantic fallback for domain matching.
Part of ARC (Adaptive Rule Context) — github.com/vasyl-pavlyuchok/arc

Called by arc-hook.py when keyword matching returns 0 domains AND
SEMANTIC_MATCHING=true is set in ~/.arc/manifest.

Usage (internal, called by arc-hook.py):
    echo '{"prompt": "...", "domains": {...}}' | python3 arc-semantic.py

Returns JSON: {"matched": {"DOMAIN": ["semantic"]}, "latency_ms": 123}

Requires: pip install sentence-transformers
Model: all-MiniLM-L6-v2 (~80MB, downloads on first use, then cached)

Latency: ~1-2s first call (model load), ~100ms subsequent (OS file cache).
Only activates when literal keyword matching fails — not every prompt.
"""
import json
import pickle
import sys
import time
from pathlib import Path

ARC_FOLDER = '.arc'
MODEL_NAME = 'all-MiniLM-L6-v2'
DEFAULT_THRESHOLD = 0.55

# Installed/relocatable ARC home — this hook lives at <ARC_HOME>/hooks/arc-semantic.py
ARC_HOME = Path(__file__).resolve().parent.parent
LEGACY_ARC_HOME = Path.home() / ARC_FOLDER


def resolve_arc_home(cwd: str = '') -> Path:
    """
    Resolve the active ARC home with the unified precedence chain:
    per-project (cwd, if given) > installed/relocatable > legacy ~/.arc.
    Always returns a Path (falls back to ARC_HOME) so the cache has a home.
    """
    if cwd:
        search_path = Path(cwd)
        for _ in range(10):
            candidate = search_path / ARC_FOLDER
            if candidate.exists() and (candidate / 'manifest').exists():
                return candidate
            if search_path.parent == search_path:
                break
            search_path = search_path.parent
    if (ARC_HOME / 'manifest').exists():
        return ARC_HOME
    if (LEGACY_ARC_HOME / 'manifest').exists():
        return LEGACY_ARC_HOME
    return ARC_HOME


def load_embeddings_cache(cache_file: Path) -> dict:
    """Load cached domain embeddings if they exist."""
    if cache_file.exists():
        try:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    return {}


def save_embeddings_cache(cache_file: Path, cache: dict) -> None:
    try:
        with open(cache_file, 'wb') as f:
            pickle.dump(cache, f)
    except Exception:
        pass


def get_manifest_mtime(arc_dir: Path) -> float:
    manifest = arc_dir / 'manifest'
    return manifest.stat().st_mtime if manifest.exists() else 0.0


def get_domain_text(domain: str, config: dict) -> str:
    """Combine domain name + recall keywords into a single text for embedding."""
    parts = [domain.lower().replace('_', ' ')]
    keywords = config.get('recall_list', [])
    parts.extend(keywords)
    return ' '.join(parts)


def main():
    t0 = time.time()

    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps({"matched": {}, "error": "invalid input"}))
        return

    prompt = input_data.get('prompt', '')
    domains = input_data.get('domains', {})
    threshold = input_data.get('threshold', DEFAULT_THRESHOLD)

    # ARC home: prefer the one the caller already resolved; else resolve via chain
    arc_home_in = input_data.get('arc_home', '')
    arc_dir = Path(arc_home_in) if arc_home_in else resolve_arc_home(input_data.get('cwd', ''))
    cache_file = arc_dir / 'embeddings.cache.pkl'

    if not prompt or not domains:
        print(json.dumps({"matched": {}}))
        return

    # Only consider active, non-always-on domains (same as keyword matching)
    candidate_domains = {
        name: cfg for name, cfg in domains.items()
        if cfg.get('state') and not cfg.get('always_on')
    }

    if not candidate_domains:
        print(json.dumps({"matched": {}}))
        return

    try:
        from sentence_transformers import SentenceTransformer, util
    except ImportError:
        print(json.dumps({"matched": {}, "error": "sentence-transformers not installed"}))
        return

    # Load or rebuild embeddings cache
    cache = load_embeddings_cache(cache_file)
    manifest_mtime = get_manifest_mtime(arc_dir)
    cache_valid = cache.get('_mtime') == manifest_mtime

    model = SentenceTransformer(MODEL_NAME)

    if not cache_valid:
        # Recompute domain embeddings
        domain_embeddings = {}
        for name, cfg in candidate_domains.items():
            text = get_domain_text(name, cfg)
            domain_embeddings[name] = model.encode(text, convert_to_tensor=True)
        cache = {'_mtime': manifest_mtime, 'domains': domain_embeddings}
        save_embeddings_cache(cache_file, cache)
    else:
        domain_embeddings = cache.get('domains', {})

    # Embed the prompt
    prompt_embedding = model.encode(prompt, convert_to_tensor=True)

    # Compare against each domain
    matched = {}
    for name, domain_emb in domain_embeddings.items():
        if name not in candidate_domains:
            continue
        score = float(util.cos_sim(prompt_embedding, domain_emb)[0][0])
        if score >= threshold:
            matched[name] = ['semantic']

    latency_ms = int((time.time() - t0) * 1000)
    print(json.dumps({"matched": matched, "latency_ms": latency_ms}))


if __name__ == '__main__':
    main()
