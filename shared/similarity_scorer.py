"""
Hybrid similarity scorer combining TF-IDF (lexical) and SBERT (semantic) embeddings.

Uses a configurable weighted average: score = alpha * tfidf + (1-alpha) * sbert
- TF-IDF catches verbatim copy-paste and structural overlap
- SBERT catches paraphrased and semantically rewritten content
"""
from typing import Dict

from shared.vectorizer import TextVectorizer


class HybridSimilarityScorer:
    """Hybrid similarity scorer for robust plagiarism detection.

    Combines lexical (TF-IDF) and semantic (SBERT) similarity scores
    using a weighted average controlled by `alpha`.
    """

    def __init__(self, model_name: str = "all-MiniLM-L12-v2", alpha: float = 0.5):
        """
        Args:
            model_name: SBERT model for semantic embeddings.
            alpha: Weight for TF-IDF score.
                   0.0 = pure semantic (SBERT), 1.0 = pure lexical (TF-IDF).
                   Default 0.5 gives equal weight to both.
        """
        self.alpha = alpha
        self.vec = TextVectorizer(model_name=model_name)

    @property
    def doc_ids(self):
        return self.vec.doc_ids

    def add_document(self, doc_id: str, text: str) -> bool:
        return self.vec.add_document(doc_id, text)

    def compute_similarity_matrix(self) -> Dict[str, Dict[str, float]]:
        """Compute pairwise hybrid similarity matrix.

        Returns a nested dict: {doc1: {doc2: score, ...}, ...}
        Scores are in [0,1].
        """
        ids = list(self.vec.doc_ids)
        if len(ids) < 2:
            return {}

        has_sbert = self.vec.use_embeddings
        has_tfidf = True

        if has_sbert and has_tfidf:
            sbert_matrix = self.vec._compute_sbert_matrix()
            tfidf_matrix = self.vec._compute_tfidf_matrix()

            if sbert_matrix and tfidf_matrix:
                matrix: Dict[str, Dict[str, float]] = {}
                for id1 in ids:
                    matrix[id1] = {}
                    for id2 in ids:
                        s = self.alpha * tfidf_matrix[id1][id2] + (1 - self.alpha) * sbert_matrix[id1][id2]
                        matrix[id1][id2] = round(s, 4)
                return matrix

        if has_sbert:
            result = self.vec._compute_sbert_matrix()
            if result:
                return result

        result = self.vec._compute_tfidf_matrix()
        if result:
            return result

        raise RuntimeError("No vectorization backend available (install scikit-learn or sentence-transformers)")

    def get_algorithm_label(self) -> str:
        label = f"Hybrid (alpha={self.alpha})"
        if self.vec.use_embeddings:
            label += f" | SBERT: {self.vec.model_name}"
        label += " | TF-IDF (lexical)"
        return label