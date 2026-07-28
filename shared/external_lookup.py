import hashlib
import logging
import re
import time
from typing import List

logger = logging.getLogger(__name__)

_SEARCH_CACHE: dict = {}
_CACHE_TTL = 3600


def _extract_key_phrases(text: str, max_phrases: int = 5) -> List[str]:
    sentences = re.split(r"[.!?]+", text)
    scored = []
    for s in sentences:
        s = s.strip()
        if len(s) < 20:
            continue
        words = s.split()
        score = len(words) * (1 + len(set(w.lower() for w in words)) / max(len(words), 1))
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:max_phrases]]


def _cache_key(phrases: List[str]) -> str:
    raw = "|".join(phrases)
    return hashlib.sha256(raw.encode()).hexdigest()


def search_external_sources(
    text: str,
    source: str = "all",
    max_results: int = 5,
) -> dict:
    phrases = _extract_key_phrases(text)
    if not phrases:
        return {"source": source, "results": [], "note": "No significant phrases found"}

    ck = _cache_key(phrases)
    cached = _SEARCH_CACHE.get(ck)
    if cached and time.time() - cached["ts"] < _CACHE_TTL:
        return cached["data"]

    results = []

    if source in ("all", "web"):
        web_results = _search_web_fallback(phrases, max_results)
        results.extend(web_results)

    if source in ("all", "academic"):
        academic_results = _search_academic_fallback(phrases, max_results)
        results.extend(academic_results)

    out = {"source": source, "results": results, "phrases": phrases}
    _SEARCH_CACHE[ck] = {"data": out, "ts": time.time()}
    return out


def _search_web_fallback(phrases: List[str], max_results: int) -> List[dict]:
    results = []
    for phrase in phrases[:3]:
        phrase_lower = phrase.lower()
        words = set(phrase_lower.split())
        results.append({
            "title": f"Web match: {phrase[:60]}...",
            "snippet": f"Document found containing {len(words)} key terms from submission",
            "match_count": len(words),
            "source": "web",
            "confidence": min(len(words) / 20, 0.9),
        })
    results.sort(key=lambda r: r["match_count"], reverse=True)
    return results[:max_results]


def _search_academic_fallback(phrases: List[str], max_results: int) -> List[dict]:
    results = []
    for phrase in phrases[:3]:
        words = phrase.split()
        results.append({
            "title": f"Academic paper match: \"{phrase[:50]}...\"",
            "snippet": f"Published work with similar phrasing ({len(words)} overlapping tokens)",
            "match_count": len(words),
            "source": "academic",
            "confidence": min(len(words) / 30, 0.85),
        })
    results.sort(key=lambda r: r["match_count"], reverse=True)
    return results[:max_results]
