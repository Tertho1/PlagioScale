"""
Text vectorizer with graceful fallback:
- Prefer sentence-transformers + faiss for best quality (if installed).
- Fallback to scikit-learn TF-IDF + cosine similarity when heavy deps are not available.

This keeps the repo runnable in lightweight environments while allowing
an upgrade path to embedding-based search later.
"""
from typing import Dict, List, Tuple
import os
import json

try:
    import numpy as np
except Exception:
    np = None

TRY_ST_MODEL = False
try:
    from sentence_transformers import SentenceTransformer
    import faiss
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
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.use_embeddings = TRY_ST_MODEL
        self.model_name = model_name
        if self.use_embeddings:
            try:
                self.model = SentenceTransformer(model_name)
            except Exception:
                self.use_embeddings = False

        # storage
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

    def compute_similarity_matrix(self) -> Dict[str, Dict[str, float]]:
        """Compute pairwise similarity between documents.

        Returns a nested dict: {doc1: {doc2: score, ...}, ...}
        Scores are in [0,1].
        """
        ids = list(self.doc_ids)
        n = len(ids)
        if n == 0:
            return {}

        # Embedding path
        if self.use_embeddings and np:
            ok = self._compute_embeddings()
            if ok and len(self.embeddings) == n:
                matrix = {i: {} for i in ids}
                for i, id1 in enumerate(ids):
                    v1 = self.embeddings[id1]
                    norm1 = np.linalg.norm(v1) + 1e-10
                    for j, id2 in enumerate(ids):
                        v2 = self.embeddings[id2]
                        score = float(np.dot(v1, v2) / (norm1 * (np.linalg.norm(v2) + 1e-10)))
                        matrix[id1][id2] = score
                return matrix

        # Fallback: TF-IDF + cosine similarity
        if SKLEARN_AVAILABLE:
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

        # Last-resort: empty similarities
        matrix = {i: {j: 0.0 for j in ids} for i in ids}
        for i in ids:
            matrix[i][i] = 1.0
        return matrix
