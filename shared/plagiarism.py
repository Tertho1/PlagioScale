"""
Plagiarism detection engine using k-shingling and TF-IDF cosine similarity.
"""
import hashlib
from math import log, sqrt
from typing import Dict, List, Set


class PlagiarismDetector:
    """Plagiarism detector using k-shingle hashing and TF-IDF cosine similarity."""

    def __init__(self, k: int = 5):
        self.k = k

    def tokenize(self, text: str) -> List[str]:
        return text.lower().split()

    def get_shingles(self, tokens: List[str]) -> Set[str]:
        shingles = set()
        for i in range(len(tokens) - self.k + 1):
            shingle = ' '.join(tokens[i:i + self.k])
            shingle_hash = hashlib.md5(shingle.encode()).hexdigest()
            shingles.add(shingle_hash)
        return shingles

    def jaccard_similarity(self, shingles1: Set[str], shingles2: Set[str]) -> float:
        if not shingles1 or not shingles2:
            return 0.0
        intersection = len(shingles1 & shingles2)
        union = len(shingles1 | shingles2)
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _compute_tfidf(tokens: List[str], doc_count: int, doc_freq: Dict[str, int]) -> Dict[str, float]:
        tf: Dict[str, float] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0.0) + 1.0
        total = len(tokens)
        result = {}
        for token, raw_tf in tf.items():
            idf = log((doc_count + 1) / (doc_freq.get(token, 0) + 1)) + 1
            result[token] = (raw_tf / total) * idf
        return result

    def cosine_similarity(self, text1: str, text2: str) -> float:
        tokens1 = self.tokenize(text1)
        tokens2 = self.tokenize(text2)

        if not tokens1 or not tokens2:
            return 0.0

        doc_freq: Dict[str, int] = {}
        for t in set(tokens1):
            doc_freq[t] = doc_freq.get(t, 0) + 1
        for t in set(tokens2):
            doc_freq[t] = doc_freq.get(t, 0) + 1
        doc_count = 2

        tfidf1 = self._compute_tfidf(tokens1, doc_count, doc_freq)
        tfidf2 = self._compute_tfidf(tokens2, doc_count, doc_freq)

        dot_product = sum(tfidf1.get(token, 0.0) * tfidf2.get(token, 0.0) for token in tfidf1 if token in tfidf2)
        mag1 = sqrt(sum(v ** 2 for v in tfidf1.values()))
        mag2 = sqrt(sum(v ** 2 for v in tfidf2.values()))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def detect(self, original_text: str, suspicious_text: str) -> dict:
        """
        Detect plagiarism between two texts.
        
        Returns:
            dict with similarity scores and detection result
        """
        tokens_orig = self.tokenize(original_text)
        tokens_susp = self.tokenize(suspicious_text)

        shingles_orig = self.get_shingles(tokens_orig)
        shingles_susp = self.get_shingles(tokens_susp)

        jaccard_sim = self.jaccard_similarity(shingles_orig, shingles_susp)
        cosine_sim = self.cosine_similarity(original_text, suspicious_text)

        # Simple plagiarism threshold
        plagiarism_score = (jaccard_sim + cosine_sim) / 2
        is_plagiarized = plagiarism_score > 0.5

        return {
            'plagiarism_score': round(plagiarism_score, 4),
            'jaccard_similarity': round(jaccard_sim, 4),
            'cosine_similarity': round(cosine_sim, 4),
            'is_plagiarized': is_plagiarized,
            'threshold': 0.5,
            'algorithm': 'k-shingle + cosine'
        }


# Example source documents (mock database)
MOCK_DATABASE = [
    """Machine learning is a subset of artificial intelligence that focuses on 
       the development of algorithms and statistical models that enable computers 
       to improve their performance on tasks through experience.""",
    """Cloud computing provides on-demand access to computing resources over the internet.
       Users can access servers, storage, and databases without maintaining physical hardware.""",
    """Distributed systems consist of multiple autonomous computers that communicate 
       through a network to achieve a common goal."""
]


def compare_with_database(suspicious_text: str, detector: PlagiarismDetector = None) -> List[dict]:
    """
    Compare suspicious text against mock database of known documents.
    """
    if detector is None:
        detector = PlagiarismDetector(k=5)

    results = []
    for idx, known_text in enumerate(MOCK_DATABASE):
        detection = detector.detect(known_text, suspicious_text)
        detection['source_id'] = idx + 1
        detection['source_preview'] = known_text[:100] + "..."
        results.append(detection)

    return results
