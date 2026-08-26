"""Lightweight lexical text comparison for on-demand API-side checks.

The worker computes full hybrid (TF-IDF + SBERT) similarity offline. These
helpers serve interactive API endpoints (draft self-check, cross-batch
comparison) where loading ML models into the memory-capped API container is
not acceptable. Pure stdlib, no dependencies.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z0-9']+")
_N = 3  # word n-gram size


def _tokens(text: str) -> list:
    return _WORD_RE.findall((text or "").lower())


def _ngrams(text: str, n: int = _N) -> set:
    toks = _tokens(text)
    if not toks:
        return set()
    if len(toks) < n:
        return {tuple(toks)}
    return {tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def similarity(a: str, b: str) -> float:
    """Lexicographic similarity in [0, 1].

    Blend of word-trigram Jaccard (penalises size differences) and containment
    (overlap / smaller-set size), which catches a short draft lifted from one
    section of a long submission.
    """
    ga, gb = _ngrams(a), _ngrams(b)
    if not ga or not gb:
        return 0.0
    inter = len(ga & gb)
    jaccard = inter / len(ga | gb)
    containment = inter / min(len(ga), len(gb))
    return round(0.6 * jaccard + 0.4 * containment, 4)
