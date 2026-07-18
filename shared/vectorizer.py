"""
Text vectorizer with graceful fallback:
- Prefer sentence-transformers for best quality (if installed).
- Fallback to scikit-learn TF-IDF + cosine similarity when heavy deps are not available.
"""
from typing import Dict, List

try:
    import numpy as np
except Exception:
    np = None

TRY_ST_MODEL = False
try:
    from sentence_transformers import SentenceTransformer
    TRY_ST_MODEL = True
except Exception:
    TRY_ST_MODEL = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except Exception:
    SKLEARN_AVAILABLE = False


class TextVectorizer:
    """Unified vectorizer interface.

    Methods:
    - add_document(doc_id, text)
    - compute_similarity_matrix() -> Dict[doc1][doc2]=score
    - _compute_tfidf_matrix() -> individual TF-IDF matrix
    - _compute_sbert_matrix() -> individual SBERT matrix
    """
    def __init__(self, model_name: str = "all-MiniLM-L12-v2"):
        self.use_embeddings = TRY_ST_MODEL
        self.model_name = model_name
        if self.use_embeddings:
            try:
                self.model = SentenceTransformer(model_name)
            except Exception:
                self.use_embeddings = False

        self.doc_texts: Dict[str, str] = {}
        self.doc_ids: List[str] = []
        self.embeddings = {}

    def add_document(self, doc_id: str, text: str) -> bool:
        if not text or len(text.strip()) < 10:
            return False
        self.doc_texts[doc_id] = text
        self.doc_ids.append(doc_id)
        return True

    def _compute_embeddings(self):
        if not self.use_embeddings:
            return False
        if not np:
            return False
        for doc_id, text in self.doc_texts.items():
            try:
                emb = self.model.encode(text, convert_to_numpy=True)
                self.embeddings[doc_id] = emb.astype('float32')
            except Exception as e:
                print(f"[Vectorizer] embedding error for {doc_id}: {e}")
        return True

    def _compute_sbert_matrix(self) -> Dict[str, Dict[str, float]]:
        if not self.use_embeddings or not np:
            return {}
        ids = list(self.doc_ids)
        n = len(ids)
        if n == 0:
            return {}
        ok = self._compute_embeddings()
        if not ok or len(self.embeddings) != n:
            return {}
        matrix = {i: {} for i in ids}
        for i, id1 in enumerate(ids):
            v1 = self.embeddings[id1]
            norm1 = np.linalg.norm(v1) + 1e-10
            for j, id2 in enumerate(ids):
                v2 = self.embeddings[id2]
                raw = float(np.dot(v1, v2) / (norm1 * (np.linalg.norm(v2) + 1e-10)))
                score = max(0.0, min(1.0, raw))
                matrix[id1][id2] = score
        return matrix

    def _compute_tfidf_matrix(self) -> Dict[str, Dict[str, float]]:
        if not SKLEARN_AVAILABLE:
            return {}
        ids = list(self.doc_ids)
        if not ids:
            return {}
        texts = [self.doc_texts[i] for i in ids]
        try:
            tf = TfidfVectorizer(stop_words='english', max_features=20000)
            X = tf.fit_transform(texts)
            sim = cosine_similarity(X)
            matrix = {}
            for i, id1 in enumerate(ids):
                matrix[id1] = {}
                for j, id2 in enumerate(ids):
                    matrix[id1][id2] = float(sim[i, j])
            return matrix
        except Exception as e:
            print(f"[Vectorizer] TF-IDF compute error: {e}")
            return {}

    def compute_similarity_matrix(self) -> Dict[str, Dict[str, float]]:
        """Compute pairwise similarity between documents.

        Prefers SBERT embeddings (semantic) if available,
        falls back to TF-IDF (lexical).

        Returns a nested dict: {doc1: {doc2: score, ...}, ...}
        Scores are in [0,1].
        """
        if not self.doc_ids:
            return {}
        sbert = self._compute_sbert_matrix()
        if sbert:
            return sbert
        tfidf = self._compute_tfidf_matrix()
        if tfidf:
            return tfidf
        raise RuntimeError("No vectorization backend available (install scikit-learn or sentence-transformers)")
