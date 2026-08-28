"""Embedding abstraction.

A Mock provider (deterministic bag-of-words vector) is used for development
so the engine runs with zero external model dependencies. A
sentence-transformers provider is available via config for production.
"""

from __future__ import annotations

import abc
import hashlib
import math
from typing import List

from app.config import settings


class EmbeddingProvider(abc.ABC):
    dimensions: int = 0

    @abc.abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        ...

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic hashing-based embedding. Stable within a process run."""

    dimensions = 64

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors = []
        for t in texts:
            vec = [0.0] * self.dimensions
            tokens = _tokenize(t)
            for tok in tokens:
                idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dimensions
                vec[idx] += 1.0
            # normalize
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class SentenceTransformersProvider(EmbeddingProvider):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # optional dep

        self._model = SentenceTransformer(model_name)
        self.dimensions = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str]) -> List[List[float]]:
        return self._model.encode(texts).tolist()


def _tokenize(text: str) -> List[str]:
    import re

    return [w for w in re.findall(r"[\w₹$%]+", text.lower())]


def create_embedding_provider() -> EmbeddingProvider:
    if settings.rag_embedding_provider == "sentence-transformers":
        return SentenceTransformersProvider(settings.rag_embedding_model or "all-MiniLM-L6-v2")
    return MockEmbeddingProvider()
