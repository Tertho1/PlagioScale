"""Tests for external lookup module."""
import time
from unittest.mock import patch
from shared.external_lookup import (
    _extract_key_phrases,
    _cache_key,
    search_external_sources,
    _SEARCH_CACHE,
)


def test_extract_key_phrases():
    text = "This is a long enough sentence to be worth extracting. Another good phrase here. Short."
    phrases = _extract_key_phrases(text, max_phrases=2)
    assert len(phrases) <= 2
    assert all(len(p) >= 20 for p in phrases)


def test_extract_key_phrases_short_text():
    phrases = _extract_key_phrases("Short.")
    assert phrases == []


def test_cache_key():
    k1 = _cache_key(["hello world"])
    k2 = _cache_key(["hello world"])
    k3 = _cache_key(["different phrase"])
    assert k1 == k2
    assert k1 != k3


def test_search_external_web():
    _SEARCH_CACHE.clear()
    result = search_external_sources(
        "This is a sufficiently long text passage that contains enough words to extract meaningful key phrases for web search.",
        source="web",
        max_results=2,
    )
    assert result["source"] == "web"
    assert len(result["results"]) > 0
    assert all(r["source"] == "web" for r in result["results"])
    assert "phrases" in result


def test_search_external_academic():
    _SEARCH_CACHE.clear()
    result = search_external_sources(
        "Another sufficiently long text passage with many words that should produce good academic matches for the lookup system.",
        source="academic",
        max_results=2,
    )
    assert result["source"] == "academic"
    assert len(result["results"]) > 0
    assert all(r["source"] == "academic" for r in result["results"])


def test_search_external_all():
    _SEARCH_CACHE.clear()
    result = search_external_sources(
        "Here is a reasonably long sentence that should trigger both web and academic search fallbacks in the external lookup module.",
        source="all",
    )
    assert result["source"] == "all"
    web_results = [r for r in result["results"] if r["source"] == "web"]
    acad_results = [r for r in result["results"] if r["source"] == "academic"]
    assert len(web_results) > 0
    assert len(acad_results) > 0


def test_search_no_phrases():
    result = search_external_sources("Hi.", source="all")
    assert "note" in result
    assert result["results"] == []


def test_search_cache():
    _SEARCH_CACHE.clear()
    text = "This is a long enough text passage to test caching behavior in the external lookup module."
    result1 = search_external_sources(text, source="web")
    assert len(_SEARCH_CACHE) == 1

    result2 = search_external_sources(text, source="web")
    assert result1 == result2
