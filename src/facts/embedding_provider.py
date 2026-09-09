"""Embedding provider abstractions for semantic entity resolution."""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import hashlib
import math
import logging

logger = logging.getLogger(__name__)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


class EmbeddingProvider(ABC):
    """Abstract base class for entity contextual embedding providers."""

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Embed a single text string into a float vector."""
        pass

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts."""
        return [self.embed(t) for t in texts]

    def similarity(self, v1: List[float], v2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        return cosine_similarity(v1, v2)


class DeterministicNgramEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding provider using character and token n-gram hashing."""

    def __init__(self, dim: int = 128):
        self.dim = dim
        self._cache: Dict[str, List[float]] = {}

    def embed(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self.dim
        cache_key = hashlib.md5(text.encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        vec = [0.0] * self.dim
        tokens = text.lower().split()
        
        for i, t in enumerate(tokens):
            h = int(hashlib.md5(t.encode("utf-8")).hexdigest()[:8], 16) % self.dim
            vec[h] += 1.0
            if i > 0:
                bigram = f"{tokens[i-1]}_{t}"
                h_bi = int(hashlib.md5(bigram.encode("utf-8")).hexdigest()[:8], 16) % self.dim
                vec[h_bi] += 1.5

        clean = "".join(c for c in text.lower() if c.isalnum() or c.isspace())
        for i in range(len(clean) - 2):
            trigram = clean[i:i+3]
            h_tri = int(hashlib.md5(trigram.encode("utf-8")).hexdigest()[:8], 16) % self.dim
            vec[h_tri] += 0.5

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]

        if len(self._cache) < 2000:
            self._cache[cache_key] = vec
        return vec


class ChromaEmbeddingProvider(EmbeddingProvider):
    """MiniLM embedding provider using Chroma's default embedding function."""

    def __init__(self):
        import chromadb.utils.embedding_functions as ef
        self.ef = ef.DefaultEmbeddingFunction()
        self._cache: Dict[str, List[float]] = {}

    def embed(self, text: str) -> List[float]:
        if not text:
            return [0.0] * 384
        key = hashlib.md5(text.encode("utf-8")).hexdigest()
        if key in self._cache:
            return self._cache[key]
        try:
            res = self.ef([text])[0]
            if hasattr(res, "tolist"):
                vec = res.tolist()
            else:
                vec = [float(x) for x in res]
            if len(self._cache) < 5000:
                self._cache[key] = vec
            return vec
        except Exception as e:
            logger.warning(f"Chroma embedding failed ({e}); falling back to n-gram.")
            fallback = DeterministicNgramEmbeddingProvider(dim=384)
            return fallback.embed(text)


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using SentenceTransformer models."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._cache: Dict[str, List[float]] = {}
        self._failed = False

    def _load_model(self):
        if self._model is None and not self._failed:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except Exception as e:
                logger.warning(f"Failed to load SentenceTransformer ({self.model_name}): {e}. Falling back.")
                self._failed = True

    def embed(self, text: str) -> List[float]:
        if not text:
            return [0.0] * 384
        cache_key = hashlib.sha256(f"{self.model_name}:{text}".encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        self._load_model()
        if self._model is not None:
            try:
                emb = self._model.encode(text, convert_to_numpy=True).tolist()
                if len(self._cache) < 5000:
                    self._cache[cache_key] = emb
                return emb
            except Exception as e:
                logger.warning(f"SentenceTransformer encoding error: {e}")

        fallback = DeterministicNgramEmbeddingProvider(dim=384)
        return fallback.embed(text)


def get_embedding_provider(prefer_chroma: bool = True) -> EmbeddingProvider:
    """Factory to acquire an active embedding provider."""
    if prefer_chroma:
        try:
            return ChromaEmbeddingProvider()
        except Exception as e:
            logger.warning(f"Could not load ChromaEmbeddingProvider ({e}), trying SentenceTransformer")

    try:
        return SentenceTransformerEmbeddingProvider()
    except Exception:
        pass

    return DeterministicNgramEmbeddingProvider()
