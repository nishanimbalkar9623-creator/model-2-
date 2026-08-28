"""Vector retriever abstraction with pluggable backing store.

- in_memory: simple cosine-search store (default, zero external deps)
- chroma / faiss: reserved for production; interface is the same

Every item carries metadata; client-specific retrieval MUST be scoped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import settings
from app.rag.embeddings import EmbeddingProvider, create_embedding_provider


@dataclass
class RetrievedItem:
    content: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class Retriever:
    def __init__(self, provider: Optional[EmbeddingProvider] = None):
        self.provider = provider or create_embedding_provider()
        # storage: list of (vector, content, metadata)
        self._docs: List[tuple] = []

    def add(self, content: str, metadata: Dict[str, Any]) -> None:
        vec = self.provider.embed_one(content)
        self._docs.append((vec, content, metadata))

    def add_many(self, items: List[Dict[str, Any]]) -> None:
        for it in items:
            self.add(it["content"], it.get("metadata", {}))

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        *,
        metadata_filter: Optional[Dict[str, Any]] = None,
        client_id: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> List[RetrievedItem]:
        k = top_k or settings.rag_top_k
        qvec = self.provider.embed_one(query)
        results: List[RetrievedItem] = []

        for vec, content, metadata in self._docs:
            if metadata_filter:
                if not all(metadata.get(kk) == vv for kk, vv in metadata_filter.items()):
                    continue
            if client_id is not None and metadata.get("client_id") != client_id:
                continue
            if source_type is not None and metadata.get("source_type") != source_type:
                continue
            score = _cosine(qvec, vec)
            results.append(RetrievedItem(content=content, score=score, metadata=metadata))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    def clear(self) -> None:
        self._docs.clear()


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)
