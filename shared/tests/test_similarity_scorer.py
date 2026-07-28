"""Tests for HybridSimilarityScorer."""
from unittest.mock import patch

import pytest

from shared.similarity_scorer import HybridSimilarityScorer


class TestHybridSimilarityScorer:
    def test_init_defaults(self):
        scorer = HybridSimilarityScorer()
        assert scorer.alpha == 0.5
        assert scorer.vec.model_name == "all-MiniLM-L12-v2"

    def test_init_custom_alpha(self):
        scorer = HybridSimilarityScorer(alpha=0.8)
        assert scorer.alpha == 0.8

    def test_add_document_short_text(self):
        scorer = HybridSimilarityScorer()
        assert scorer.add_document("id1", "short") is False
        assert len(scorer.doc_ids) == 0

    def test_add_document_valid(self):
        scorer = HybridSimilarityScorer()
        assert scorer.add_document("id1", "this is a valid document with enough text") is True
        assert len(scorer.doc_ids) == 1

    def test_empty_matrix(self):
        scorer = HybridSimilarityScorer()
        assert scorer.compute_similarity_matrix() == {}

    def test_single_document(self):
        scorer = HybridSimilarityScorer()
        scorer.add_document("id1", "some text that is long enough for vectorization")
        assert scorer.compute_similarity_matrix() == {}

    def test_two_identical_documents_tfidf(self):
        scorer = HybridSimilarityScorer()
        text = "this is a test document with enough text for vectorization purposes"
        scorer.add_document("id1", text)
        scorer.add_document("id2", text)
        matrix = scorer.compute_similarity_matrix()
        assert matrix["id1"]["id2"] == pytest.approx(1.0, abs=0.001)
        assert matrix["id2"]["id1"] == pytest.approx(1.0, abs=0.001)
        assert matrix["id1"]["id1"] == pytest.approx(1.0, abs=0.001)

    def test_two_different_documents(self):
        scorer = HybridSimilarityScorer()
        scorer.add_document("id1", "machine learning is a subset of artificial intelligence")
        scorer.add_document(
            "id2", "quantum physics deals with subatomic particles and wave functions"
        )
        matrix = scorer.compute_similarity_matrix()
        score = matrix["id1"]["id2"]
        assert 0.0 <= score <= 1.0
        assert score < matrix["id1"]["id1"]

    def test_partial_overlap(self):
        scorer = HybridSimilarityScorer()
        scorer.add_document("id1", "the quick brown fox jumps over the lazy dog")
        scorer.add_document("id2", "the quick brown fox leaps over the lazy dog")
        matrix = scorer.compute_similarity_matrix()
        score = matrix["id1"]["id2"]
        assert 0.5 < score < 1.0

    def test_three_documents_shape(self):
        scorer = HybridSimilarityScorer()
        docs = [
            "the quick brown fox jumps over the lazy dog near the riverbank",
            "the quick brown fox leaps over the lazy canine by the river",
            "quantum entanglement is a strange phenomenon in modern physics",
        ]
        for i, text in enumerate(docs):
            scorer.add_document(f"doc{i}", text)
        matrix = scorer.compute_similarity_matrix()
        assert len(matrix) == 3
        for doc_id in ["doc0", "doc1", "doc2"]:
            assert len(matrix[doc_id]) == 3

    def test_get_algorithm_label(self):
        scorer = HybridSimilarityScorer()
        label = scorer.get_algorithm_label()
        assert "Hybrid" in label
        assert "alpha=0.5" in label
        assert "TF-IDF" in label

    def test_alpha_pure_tfidf(self):
        scorer = HybridSimilarityScorer(alpha=1.0)
        text = "the quick brown fox jumps over the lazy dog"
        scorer.add_document("id1", text)
        scorer.add_document("id2", text)
        matrix = scorer.compute_similarity_matrix()
        assert matrix["id1"]["id2"] == pytest.approx(1.0, abs=0.001)
        label = scorer.get_algorithm_label()
        assert "alpha=1.0" in label


class TestHybridSimilarityScorerMocked:
    """Tests that mock the SBERT path to verify alpha blending."""

    def test_alpha_blending_equal_weights(self):
        scorer = HybridSimilarityScorer(alpha=0.5)
        scorer.vec.use_embeddings = True
        scorer.add_document("id1", "some text with enough length for the vectorizer")
        scorer.add_document("id2", "some other text that is also sufficiently long")

        fake_tfidf = {"id1": {"id1": 1.0, "id2": 0.6}, "id2": {"id1": 0.6, "id2": 1.0}}
        fake_sbert = {"id1": {"id1": 1.0, "id2": 0.4}, "id2": {"id1": 0.4, "id2": 1.0}}

        with patch.object(scorer.vec, "_compute_tfidf_matrix", return_value=fake_tfidf), \
             patch.object(scorer.vec, "_compute_sbert_matrix", return_value=fake_sbert):
            matrix = scorer.compute_similarity_matrix()
            assert matrix["id1"]["id2"] == pytest.approx(0.5, abs=0.001)
            assert matrix["id1"]["id1"] == pytest.approx(1.0, abs=0.001)

    def test_alpha_skewed_tfidf(self):
        scorer = HybridSimilarityScorer(alpha=0.8)
        scorer.vec.use_embeddings = True
        scorer.add_document("id1", "some text with enough length for the vectorizer")
        scorer.add_document("id2", "some other text that is also sufficiently long")

        fake_tfidf = {"id1": {"id1": 1.0, "id2": 0.7}, "id2": {"id1": 0.7, "id2": 1.0}}
        fake_sbert = {"id1": {"id1": 1.0, "id2": 0.3}, "id2": {"id1": 0.3, "id2": 1.0}}

        with patch.object(scorer.vec, "_compute_tfidf_matrix", return_value=fake_tfidf), \
             patch.object(scorer.vec, "_compute_sbert_matrix", return_value=fake_sbert):
            matrix = scorer.compute_similarity_matrix()
            expected = 0.8 * 0.7 + 0.2 * 0.3
            assert matrix["id1"]["id2"] == pytest.approx(expected, abs=0.001)

    def test_alpha_pure_sbert(self):
        scorer = HybridSimilarityScorer(alpha=0.0)
        scorer.vec.use_embeddings = True
        scorer.add_document("id1", "some text with enough length for the vectorizer")
        scorer.add_document("id2", "some other text that is also sufficiently long")

        fake_tfidf = {"id1": {"id1": 1.0, "id2": 0.9}, "id2": {"id1": 0.9, "id2": 1.0}}
        fake_sbert = {"id1": {"id1": 1.0, "id2": 0.3}, "id2": {"id1": 0.3, "id2": 1.0}}

        with patch.object(scorer.vec, "_compute_tfidf_matrix", return_value=fake_tfidf), \
             patch.object(scorer.vec, "_compute_sbert_matrix", return_value=fake_sbert):
            matrix = scorer.compute_similarity_matrix()
            assert matrix["id1"]["id2"] == pytest.approx(0.3, abs=0.001)

    def test_fallback_to_tfidf_when_sbert_fails(self):
        scorer = HybridSimilarityScorer(alpha=0.5)
        scorer.vec.use_embeddings = True
        scorer.vec.doc_ids = ["id1", "id2"]
        scorer.vec.doc_texts = {
            "id1": "the quick brown fox jumps over the lazy dog",
            "id2": "the quick brown fox leaps over the lazy dog",
        }

        with patch.object(scorer.vec, "_compute_sbert_matrix", return_value={}):
            matrix = scorer.compute_similarity_matrix()
            assert 0.5 < matrix["id1"]["id2"] < 1.0
