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

ARC_DIR = Path.home() / '.arc'
CACHE_FILE = ARC_DIR / 'embeddings.cache.pkl'
MODEL_NAME = 'all-MiniLM-L6-v2'
DEFAULT_THRESHOLD = 0.55


def load_embeddings_cache() -> dict:
    """Load cached domain embeddings if they exist."""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    return {}


def save_embeddings_cache(cache: dict) -> None:
    try:
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(cache, f)
    except Exception:
        pass


def get_manifest_mtime() -> float:
    manifest = ARC_DIR / 'manifest'
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
    cache = load_embeddings_cache()
    manifest_mtime = get_manifest_mtime()
    cache_valid = cache.get('_mtime') == manifest_mtime

    model = SentenceTransformer(MODEL_NAME)

    if not cache_valid:
        # Recompute domain embeddings
        domain_embeddings = {}
        for name, cfg in candidate_domains.items():
            text = get_domain_text(name, cfg)
            domain_embeddings[name] = model.encode(text, convert_to_tensor=True)
        cache = {'_mtime': manifest_mtime, 'domains': domain_embeddings}
        save_embeddings_cache(cache)
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
