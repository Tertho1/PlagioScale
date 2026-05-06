"""
Plagiarism detection engine using k-shingling and cosine similarity.
"""
import hashlib
from collections import Counter
from math import sqrt
from typing import Set, List, Tuple


class PlagiarismDetector:
    """Simple plagiarism detector using k-shingle hashing and cosine similarity."""
    
    def __init__(self, k: int = 5):
        """
        Initialize detector.
        
        Args:
            k: Shingle size (number of tokens per shingle)
        """
        self.k = k
    
    def tokenize(self, text: str) -> List[str]:
        """Tokenize text into words."""
        return text.lower().split()
    
    def get_shingles(self, tokens: List[str]) -> Set[str]:
        """Generate k-shingles from tokens."""
        shingles = set()
        for i in range(len(tokens) - self.k + 1):
            shingle = ' '.join(tokens[i:i + self.k])
            shingle_hash = hashlib.md5(shingle.encode()).hexdigest()
            shingles.add(shingle_hash)
        return shingles
    
    def jaccard_similarity(self, shingles1: Set[str], shingles2: Set[str]) -> float:
        """Calculate Jaccard similarity between two shingle sets."""
        if not shingles1 or not shingles2:
            return 0.0
        
        intersection = len(shingles1 & shingles2)
        union = len(shingles1 | shingles2)
        
        return intersection / union if union > 0 else 0.0
    
    def cosine_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate cosine similarity using term frequency.
        """
        tokens1 = self.tokenize(text1)
        tokens2 = self.tokenize(text2)
        
        if not tokens1 or not tokens2:
            return 0.0
        
        freq1 = Counter(tokens1)
        freq2 = Counter(tokens2)
        
        # Calculate dot product
        dot_product = sum(freq1[token] * freq2[token] for token in freq1 if token in freq2)
        
        # Calculate magnitudes
        mag1 = sqrt(sum(count ** 2 for count in freq1.values()))
        mag2 = sqrt(sum(count ** 2 for count in freq2.values()))
        
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
