import pytest

from shared.vectorizer import TextVectorizer


class TestTextVectorizer:
    def setup_method(self):
        self.vec = TextVectorizer()

    def test_add_document_short_text(self):
        ok = self.vec.add_document("id1", "short")
        assert ok is False
        assert len(self.vec.doc_ids) == 0

    def test_add_document_valid(self):
        ok = self.vec.add_document("id1", "this is a valid document with enough text")
        assert ok is True
        assert "id1" in self.vec.doc_texts

    def test_add_document_empty(self):
        ok = self.vec.add_document("id1", "")
        assert ok is False

    def test_add_document_whitespace_only(self):
        ok = self.vec.add_document("id1", "   ")
        assert ok is False

    def test_empty_matrix(self):
        matrix = self.vec.compute_similarity_matrix()
        assert matrix == {}

    def test_single_document_self_similarity(self):
        self.vec.add_document("id1", "this is a test document with enough text for vectorization")
        matrix = self.vec.compute_similarity_matrix()
        assert matrix["id1"]["id1"] == pytest.approx(1.0, abs=0.001)

    def test_identical_documents(self):
        text = "this is a test document with enough text for vectorization purposes"
        self.vec.add_document("id1", text)
        self.vec.add_document("id2", text)
        matrix = self.vec.compute_similarity_matrix()
        assert matrix["id1"]["id2"] == pytest.approx(1.0, abs=0.001)
        assert matrix["id2"]["id1"] == pytest.approx(1.0, abs=0.001)

    def test_different_documents(self):
        self.vec.add_document("id1", "machine learning is a subset of artificial intelligence")
        self.vec.add_document(
            "id2", "quantum physics deals with subatomic particles and wave functions"
        )
        matrix = self.vec.compute_similarity_matrix()
        score = matrix["id1"]["id2"]
        assert 0.0 <= score <= 1.0, f"Score {score} not in [0, 1]"
        assert score < matrix["id1"]["id1"]

    def test_multiple_documents_shape(self):
        docs = [
            "the quick brown fox jumps over the lazy dog near the riverbank",
            "the quick brown fox leaps over the lazy canine by the river",
            "quantum entanglement is a strange phenomenon in modern physics",
        ]
        for i, text in enumerate(docs):
            self.vec.add_document(f"doc{i}", text)
        matrix = self.vec.compute_similarity_matrix()
        assert len(matrix) == 3
        for doc_id in ["doc0", "doc1", "doc2"]:
            assert len(matrix[doc_id]) == 3

    def test_partial_overlap(self):
        self.vec.add_document("id1", "the quick brown fox jumps over the lazy dog")
        self.vec.add_document("id2", "the quick brown fox leaps over the lazy dog")
        matrix = self.vec.compute_similarity_matrix()
        score = matrix["id1"]["id2"]
        assert 0.5 < score < 1.0, f"Expected partial overlap, got {score}"
