import pytest

from shared.plagiarism import PlagiarismDetector, compare_with_database


class TestPlagiarismDetector:
    def setup_method(self):
        self.detector = PlagiarismDetector(k=3)

    def test_tokenize_empty(self):
        assert self.detector.tokenize("") == []

    def test_tokenize_basic(self):
        assert self.detector.tokenize("Hello World") == ["hello", "world"]

    def test_get_shingles_short_text(self):
        tokens = ["a", "b"]
        shingles = self.detector.get_shingles(tokens)
        assert shingles == set()

    def test_get_shingles_normal(self):
        tokens = ["a", "b", "c", "d"]
        shingles = self.detector.get_shingles(tokens)
        assert len(shingles) == 2

    def test_jaccard_identical(self):
        s = {"a", "b", "c"}
        assert self.detector.jaccard_similarity(s, s) == 1.0

    def test_jaccard_disjoint(self):
        s1 = {"a", "b"}
        s2 = {"c", "d"}
        assert self.detector.jaccard_similarity(s1, s2) == 0.0

    def test_jaccard_empty(self):
        assert self.detector.jaccard_similarity(set(), {"a"}) == 0.0
        assert self.detector.jaccard_similarity({"a"}, set()) == 0.0

    def test_cosine_identical(self):
        score = self.detector.cosine_similarity("hello world", "hello world")
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_cosine_disjoint(self):
        score = self.detector.cosine_similarity("hello world", "foo bar")
        assert score == 0.0

    def test_cosine_empty(self):
        assert self.detector.cosine_similarity("", "hello") == 0.0
        assert self.detector.cosine_similarity("hello", "") == 0.0
        assert self.detector.cosine_similarity("", "") == 0.0

    def test_cosine_partial_overlap(self):
        score = self.detector.cosine_similarity("hello world", "hello there")
        assert 0 < score < 1.0

    def test_detect_identical(self):
        text = "machine learning is a powerful tool for data analysis"
        result = self.detector.detect(text, text)
        assert result["plagiarism_score"] == pytest.approx(1.0, abs=1e-6)
        assert result["is_plagiarized"] is True

    def test_detect_different(self):
        result = self.detector.detect("machine learning", "quantum physics")
        assert result["plagiarism_score"] < 0.5
        assert result["is_plagiarized"] is False

    def test_detect_short_texts(self):
        result = self.detector.detect("hi", "bye")
        assert result["plagiarism_score"] == 0.0
        assert result["is_plagiarized"] is False

    def test_detect_keys(self):
        result = self.detector.detect("some text", "other text")
        expected_keys = {
            "plagiarism_score", "jaccard_similarity", "cosine_similarity",
            "is_plagiarized", "threshold", "algorithm",
        }
        assert expected_keys.issubset(result.keys())

    def test_compare_with_database(self):
        results = compare_with_database("machine learning is a subset")
        assert len(results) == 3
        for r in results:
            assert "source_id" in r
            assert "source_preview" in r
            assert "plagiarism_score" in r
