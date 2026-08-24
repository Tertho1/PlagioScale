"""AI content detection using composite hybrid approach.

Phase 2 architecture:
  Primary:   RoBERTa classifier (Hello-SimpleAI/chatgpt-detector-roberta)
  Secondary: DistilGPT2 perplexity + burstiness
  Tertiary:  5 stylometric features
  Final:     Weighted blend → ai_score [0, 1]
"""

from __future__ import annotations

import concurrent.futures
import logging
import math
import re
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Limit torch to a single thread once at module load (global setting, not per-call)
try:
    import torch as _torch
    _torch.set_num_threads(1)
except ImportError:
    _torch = None

_ROBERTA_MODEL = "Hello-SimpleAI/chatgpt-detector-roberta"
_GPT2_MODEL = "distilgpt2"

# Weights for composite score (must sum to 1.0)
_W_ROBERTA = 0.50
_W_PPL_BURST = 0.30
_W_STYLO = 0.20

# Thresholds for perplexity and burstiness normalization
_PPL_LOW = 15.0   # below this → very predictable → likely AI
_PPL_HIGH = 60.0  # above this → very surprising → likely human
_BURST_LOW = 0.1  # below this → uniform → likely AI
_BURST_HIGH = 0.8 # above this → varied → likely human

# Stylometric feature weights (within the stylo sub-score)
_STYLO_WEIGHTS = {
    "ttr": 0.20,
    "sentence_len_var": 0.20,
    "transition_words": 0.25,
    "hedge_words": 0.15,
    "passive_rate": 0.20,
}

_TRANSITION_WORDS = {
    "firstly", "secondly", "thirdly", "furthermore", "moreover", "additionally",
    "in addition", "further", "also", "finally", "lastly", "consequently",
    "therefore", "thus", "hence", "nevertheless", "nonetheless", "however",
    "meanwhile", "subsequently", "in conclusion", "to summarize", "as a result",
    "notably", "specifically", "particularly", "importantly", "significantly",
}

_HEDGE_WORDS = {
    "perhaps", "maybe", "possibly", "probably", "likely", "seems", "appears",
    "might", "may", "could", "would", "suggests", "indicates", "tends",
    "generally", "relatively", "somewhat", "fairly", "quite", "rather",
    "arguably", "presumably", "approximately", "roughly",
}


class AIContentDetector:
    """Composite hybrid AI content detector.

    Blends three signal groups into a final ai_score in [0, 1]:
      - RoBERTa classifier (50%)
      - Perplexity + burstiness via DistilGPT2 (30%)
      - Stylometric features (20%)

    Higher score = more likely AI-written.
    """

    _instance: Optional["AIContentDetector"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "AIContentDetector":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._roberta_pipeline = None
                cls._instance._gpt2_tokenizer = None
                cls._instance._gpt2_model = None
                cls._instance._loaded = False
                cls._instance._load_lock = threading.Lock()
        return cls._instance

    def __init__(self) -> None:
        pass

    def _ensure_loaded(self) -> None:
        """Lazy-load models on first use instead of at instantiation time."""
        if self._loaded:
            return
        with self._load_lock:
            if self._loaded:
                return
            self._load_models()

    def _load_models(self) -> None:
        try:
            from transformers import pipeline

            self._roberta_pipeline = pipeline(
                "text-classification",
                model=_ROBERTA_MODEL,
                truncation=True,
                max_length=512,
            )
            logger.info(
                "RoBERTa detector loaded: %s (%d params)",
                _ROBERTA_MODEL,
                self._roberta_pipeline.model.num_parameters(),
            )
        except Exception as exc:
            logger.warning("RoBERTa detector failed to load: %s", exc)
            self._roberta_pipeline = None
        finally:
            self._loaded = True

    def _load_gpt2(self) -> None:
        """Lazy-load DistilGPT2 for perplexity scoring."""
        if self._gpt2_model is not None:
            return
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            # Try loading from cache first (local_files_only) to avoid HF timeouts
            try:
                self._gpt2_tokenizer = AutoTokenizer.from_pretrained(
                    _GPT2_MODEL, local_files_only=True
                )
                model = AutoModelForCausalLM.from_pretrained(
                    _GPT2_MODEL, local_files_only=True
                )
            except Exception:
                # Fall back to online (will download if not cached)
                self._gpt2_tokenizer = AutoTokenizer.from_pretrained(_GPT2_MODEL)
                model = AutoModelForCausalLM.from_pretrained(_GPT2_MODEL)

            # Check if model landed on meta device (newer transformers lazy-load)
            param = next(model.parameters(), None)
            if param is not None and param.device.type == 'meta':
                logger.warning("GPT2 model on meta device — reloading with explicit device")
                model = AutoModelForCausalLM.from_pretrained(_GPT2_MODEL)

            model = model.to("cpu")
            model.eval()
            self._gpt2_model = model
            logger.info("DistilGPT2 loaded for perplexity scoring")
        except Exception as exc:
            logger.warning("DistilGPT2 failed to load: %s", exc)
            self._gpt2_model = None
            self._gpt2_tokenizer = None

    # ---- Public API ----

    @property
    def available(self) -> bool:
        return self._roberta_pipeline is not None

    def detect(self, text: str, timeout: float = 120.0) -> float:
        """Run composite AI detection on text.

        Returns score in [0, 1]:
          0.0  → confidently human
          1.0  → confidently AI
         -1.0  → detection unavailable or timed out

        Args:
            timeout: max seconds for the whole detection; on expiry returns -1.0.
        """
        if not text or not text.strip():
            return 0.0
        if self._roberta_pipeline is None:
            self._ensure_loaded()
        if not self.available:
            return -1.0

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._detect_composite, text)
                return round(
                    max(0.0, min(1.0, future.result(timeout=timeout))), 4
                )
        except concurrent.futures.TimeoutError:
            logger.warning("AI detection timed out after %.0fs", timeout)
            return -1.0
        except Exception as exc:
            logger.warning("AI detection failed: %s", exc)
            return -1.0

    def _detect_composite(self, text: str) -> float:
        r_score = self._roberta_score(text)
        ppl, burst = self._perplexity_burstiness(text)
        stylo = self._stylometric_features(text)

        ppl_score = self._normalize_ppl(ppl)
        burst_score = self._normalize_burst(burst)
        secondary_score = 0.7 * ppl_score + 0.3 * burst_score

        stylo_score = self._normalize_stylometric(stylo)

        composite = (
            _W_ROBERTA * r_score
            + _W_PPL_BURST * secondary_score
            + _W_STYLO * stylo_score
        )
        return max(0.0, min(1.0, composite))

    # ---- Primary: RoBERTa ----

    def _roberta_score(self, text: str) -> float:
        if not self._roberta_pipeline:
            return 0.5
        result = self._roberta_pipeline(text[:5000])[0]
        label: str = result["label"]
        score: float = result["score"]
        # Invert for "Human" label so higher = more AI-like
        if label.lower() == "human":
            return 1.0 - score
        return score

    # ---- Secondary: Perplexity + Burstiness ----

    def _perplexity_burstiness(self, text: str) -> tuple[float, float]:
        self._load_gpt2()
        if self._gpt2_model is None:
            return 30.0, 0.3  # neutral fallback

        # Single-pass perplexity on full text (no per-sentence loop — too slow on CPU)
        ppl = self._perplexity_of(text)

        # Statistical burstiness from sentence-length variance (microseconds, no neural net)
        sentences = self._split_sentences(text)
        if len(sentences) >= 2:
            sent_lens = [len(s.split()) for s in sentences]
            mean_len = sum(sent_lens) / len(sent_lens)
            if mean_len > 1e-8:
                variance = sum((sl - mean_len) ** 2 for sl in sent_lens) / len(sent_lens)
                burst = math.sqrt(variance) / mean_len
            else:
                burst = 0.0
        else:
            burst = 0.0

        return ppl, burst

    def _perplexity_of(self, text: str) -> float:
        import torch

        try:
            inputs = self._gpt2_tokenizer(
                text, return_tensors="pt", truncation=True, max_length=512
            )
            with torch.no_grad():
                outputs = self._gpt2_model(**inputs, labels=inputs["input_ids"])
            loss = outputs.loss
            if loss is None:
                return 30.0
            if hasattr(loss, 'device') and 'meta' in str(loss.device):
                logger.warning("Meta tensor detected in perplexity — returning neutral value")
                return 30.0
            return float(torch.exp(loss).item())
        except Exception as exc:
            logger.warning("Perplexity computation failed: %s", exc)
            return 30.0

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        raw = re.split(r"[.!?]+", text)
        return [s.strip() for s in raw if len(s.strip()) > 10]

    @staticmethod
    def _normalize_ppl(ppl: float) -> float:
        if ppl <= _PPL_LOW:
            return 1.0
        if ppl >= _PPL_HIGH:
            return 0.0
        return 1.0 - (ppl - _PPL_LOW) / (_PPL_HIGH - _PPL_LOW)

    @staticmethod
    def _normalize_burst(burst: float) -> float:
        if burst <= _BURST_LOW:
            return 1.0
        if burst >= _BURST_HIGH:
            return 0.0
        return 1.0 - (burst - _BURST_LOW) / (_BURST_HIGH - _BURST_LOW)

    # ---- Tertiary: Stylometric Features ----

    @staticmethod
    def _stylometric_features(text: str) -> dict[str, float]:
        words = text.lower().split()
        n_words = len(words)
        if n_words < 10:
            return {"ttr": 0.5, "sentence_len_var": 0.5, "transition_words": 0.5, "hedge_words": 0.5, "passive_rate": 0.5}

        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        n_sents = len(sentences) or 1

        unique_words = len(set(words))
        ttr = unique_words / n_words

        sent_lens = [len(s.split()) for s in sentences]
        mean_len = sum(sent_lens) / n_sents
        sent_var = math.sqrt(sum((sl - mean_len) ** 2 for sl in sent_lens) / n_sents) / (mean_len + 1e-8)

        multi_word_in_text = any(tw in text.lower() for tw in _TRANSITION_WORDS if " " in tw)
        trans_count = sum(1 for w in words if w in _TRANSITION_WORDS or multi_word_in_text)
        trans_rate = trans_count / (n_words + 1)

        hedge_count = sum(1 for w in words if w in _HEDGE_WORDS)
        hedge_rate = hedge_count / (n_words + 1)

        passive_count = len(re.findall(r"\b(?:is|are|was|were|be|been|being)\s+\w+ed\b", text.lower()))
        passive_rate = passive_count / (n_words + 1)

        return {
            "ttr": ttr,
            "sentence_len_var": sent_var,
            "transition_words": trans_rate,
            "hedge_words": hedge_rate,
            "passive_rate": passive_rate,
        }

    @staticmethod
    def _normalize_stylometric(feats: dict) -> float:
        raw = {}
        raw["ttr"] = 1.0 - min(feats["ttr"], 1.0)  # low TTR → more AI-like
        raw["sentence_len_var"] = 1.0 - min(feats["sentence_len_var"], 1.0)  # low variance → AI-like
        raw["transition_words"] = min(feats["transition_words"] * 10, 1.0)  # high transitions → AI-like
        raw["hedge_words"] = 1.0 - min(feats["hedge_words"] * 10, 1.0)  # low hedge → AI-like
        raw["passive_rate"] = min(feats["passive_rate"] * 20, 1.0)  # high passive → AI-like

        score = sum(raw[k] * _STYLO_WEIGHTS[k] for k in _STYLO_WEIGHTS)
        return max(0.0, min(1.0, score))
