"""Tests for AI content detection module."""
from unittest.mock import MagicMock

from shared.ai_detector import AIContentDetector


def test_singleton():
    d1 = AIContentDetector()
    d2 = AIContentDetector()
    assert d1 is d2


def test_available_no_pipeline():
    d = AIContentDetector()
    d._roberta_pipeline = None
    assert d.available is False


def test_detect_empty_text():
    d = AIContentDetector()
    d._roberta_pipeline = MagicMock()
    assert d.detect("") == 0.0
    assert d.detect("   ") == 0.0


def test_detect_unavailable():
    d = AIContentDetector()
    d._roberta_pipeline = None
    assert d.detect("some text") == -1.0


def test_roberta_score_human_label():
    d = AIContentDetector()
    mock_pipeline = MagicMock()
    mock_pipeline.return_value = [{"label": "Human", "score": 0.3}]
    d._roberta_pipeline = mock_pipeline
    score = d._roberta_score("test text")
    assert score == 0.7


def test_roberta_score_ai_label():
    d = AIContentDetector()
    mock_pipeline = MagicMock()
    mock_pipeline.return_value = [{"label": "AI", "score": 0.85}]
    d._roberta_pipeline = mock_pipeline
    score = d._roberta_score("test text")
    assert score == 0.85


def test_roberta_score_no_pipeline():
    d = AIContentDetector()
    d._roberta_pipeline = None
    assert d._roberta_score("test") == 0.5


def test_perplexity_fallback():
    d = AIContentDetector()
    d._gpt2_model = None
    d._load_gpt2 = MagicMock()
    ppl, burst = d._perplexity_burstiness("test sentence here")
    assert ppl == 30.0
    assert burst == 0.3


def test_split_sentences():
    result = AIContentDetector._split_sentences("Hello world. This is a longer sentence! Short.")
    assert len(result) == 2
    assert all(len(s) > 10 for s in result)


def test_normalize_ppl():
    assert AIContentDetector._normalize_ppl(5.0) == 1.0
    assert AIContentDetector._normalize_ppl(15.0) == 1.0
    assert AIContentDetector._normalize_ppl(37.5) == 0.5
    assert AIContentDetector._normalize_ppl(60.0) == 0.0
    assert AIContentDetector._normalize_ppl(100.0) == 0.0


def test_normalize_burst():
    assert AIContentDetector._normalize_burst(0.05) == 1.0
    assert AIContentDetector._normalize_burst(0.1) == 1.0
    assert AIContentDetector._normalize_burst(0.45) == 0.5
    assert AIContentDetector._normalize_burst(0.8) == 0.0
    assert AIContentDetector._normalize_burst(1.0) == 0.0


def test_stylometric_features_short_text():
    feats = AIContentDetector._stylometric_features("short")
    assert feats["ttr"] == 0.5
    assert feats["sentence_len_var"] == 0.5
    assert feats["transition_words"] == 0.5


def test_stylometric_features_normal():
    feats = AIContentDetector._stylometric_features(
        "This is a test sentence. Here is another one. Finally a third sentence for testing."
    )
    assert 0 <= feats["ttr"] <= 1
    assert feats["sentence_len_var"] >= 0


def test_stylometric_features_with_transitions():
    feats = AIContentDetector._stylometric_features(
        "Firstly this is a sentence. Furthermore it has transition words. Consequently the result should be high."
    )
    assert feats["transition_words"] > 0


def test_stylometric_features_with_hedges():
    feats = AIContentDetector._stylometric_features(
        "This is perhaps a test. Maybe it has hedge words. The result might indicate hedging."
    )
    assert feats["hedge_words"] > 0


def test_normalize_stylometric():
    feats = {"ttr": 0.8, "sentence_len_var": 0.7, "transition_words": 0.05, "hedge_words": 0.02, "passive_rate": 0.03}
    score = AIContentDetector._normalize_stylometric(feats)
    assert 0 <= score <= 1


def test_detect_with_mocked_pipeline():
    d = AIContentDetector()
    d._roberta_pipeline = MagicMock()
    d._roberta_pipeline.return_value = [{"label": "AI", "score": 0.9}]
    d._load_gpt2 = MagicMock()
    d._gpt2_model = None

    score = d.detect("A sufficiently long text passage to analyze for AI detection testing purposes.")
    assert 0 <= score <= 1.0
