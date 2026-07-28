"""
Hybrid similarity scorer combining TF-IDF (lexical), SBERT (semantic) embeddings,
and Jaccard n-gram overlap.

Blends three signals:
  score = w_tfidf * tfidf + w_sbert * sbert + w_jac * jaccard
- TF-IDF catches verbatim copy-paste and structural overlap
- SBERT catches paraphrased and semantically rewritten content
- Jaccard n-gram catches phrase-level repetition
"""
from typing import Dict

from shared.vectorizer import TextVectorizer


class HybridSimilarityScorer:
    """Hybrid similarity scorer for robust plagiarism detection.

    Combines lexical (TF-IDF), semantic (SBERT), and n-gram (Jaccard) scores.
    """

    def __init__(self, model_name: str = "all-MiniLM-L12-v2",
                 alpha: float = 0.5, jaccard_weight: float = 0.15,
                 jaccard_n: int = 2):
        """
        Args:
            model_name: SBERT model for semantic embeddings.
            alpha: Weight distribution between TF-IDF and SBERT
                   within the (TF-IDF + SBERT) portion.
                   0.0 = pure semantic, 1.0 = pure lexical.
            jaccard_weight: Overall weight for Jaccard n-gram signal.
                            The (TF-IDF + SBERT) portion gets (1 - jaccard_weight).
            jaccard_n: n-gram size for Jaccard (2 = bigrams).
        """
        self.alpha = alpha
        self.jaccard_weight = jaccard_weight
        self.jaccard_n = jaccard_n
        self.vec = TextVectorizer(model_name=model_name)

    @property
    def doc_ids(self):
        return self.vec.doc_ids

    def add_document(self, doc_id: str, text: str) -> bool:
        return self.vec.add_document(doc_id, text)

    def compute_similarity_matrix(self) -> Dict[str, Dict[str, float]]:
        """Compute pairwise hybrid similarity matrix.

        Blends TF-IDF, SBERT, and Jaccard n-gram signals.

        Returns a nested dict: {doc1: {doc2: score, ...}, ...}
        Scores are in [0,1].
        """
        ids = list(self.vec.doc_ids)
        if len(ids) < 2:
            return {}

        has_sbert = self.vec.use_embeddings
        has_tfidf = True

        sbert_matrix = self.vec._compute_sbert_matrix() if has_sbert else {}
        tfidf_matrix = self.vec._compute_tfidf_matrix() if has_tfidf else {}
        jac_matrix = self.vec._compute_jaccard_matrix(n=self.jaccard_n)

        if not tfidf_matrix and not sbert_matrix:
            if jac_matrix:
                return jac_matrix
            raise RuntimeError("No vectorization backend available")

        w_jac = self.jaccard_weight
        w_rest = 1.0 - w_jac
        w_tfidf = self.alpha * w_rest
        w_sbert = (1.0 - self.alpha) * w_rest

        matrix: Dict[str, Dict[str, float]] = {}
        for id1 in ids:
            matrix[id1] = {}
            for id2 in ids:
                s = 0.0
                if tfidf_matrix and id1 in tfidf_matrix and id2 in tfidf_matrix[id1]:
                    s += w_tfidf * tfidf_matrix[id1][id2]
                if sbert_matrix and id1 in sbert_matrix and id2 in sbert_matrix[id1]:
                    s += w_sbert * sbert_matrix[id1][id2]
                if jac_matrix and id1 in jac_matrix and id2 in jac_matrix[id1]:
                    s += w_jac * jac_matrix[id1][id2]
                matrix[id1][id2] = round(s, 4)
        return matrix

    def get_algorithm_label(self) -> str:
        label = f"Hybrid (alpha={self.alpha}, jaccard_w={self.jaccard_weight})"
        if self.vec.use_embeddings:
            label += f" | SBERT: {self.vec.model_name}"
        label += " | TF-IDF (lexical)"
        label += f" | Jaccard-{self.jaccard_n}gram"
        return label
