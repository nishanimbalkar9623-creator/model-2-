"""Client document search.

Documents themselves live in the Backend. This module holds an in-memory
index of document *chunks/metadata* that the backend shares with the engine
(via an ingestion endpoint or the search tool result cache) and performs
client-scoped semantic search over it.

Documents are treated as DATA, never as instructions (prompt-injection safe).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from app.rag.embeddings import EmbeddingProvider, create_embedding_provider
from app.rag.retriever import RetrievedItem, Retriever
from app.safety.permissions import ClientIsolationViolation
from app.schemas.agent import UserContext


class ClientDocumentStore:
    def __init__(self, provider: Optional[EmbeddingProvider] = None):
        self._retriever = Retriever(provider or create_embedding_provider())

    def index_chunk(
        self,
        *,
        content: str,
        client_id: str,
        document_id: str,
        title: str,
        page: Optional[int] = None,
        created_at: Optional[str] = None,
        url: Optional[str] = None,
    ) -> None:
        self._retriever.add(
            content,
            {
                "source_type": "client_document",
                "client_id": client_id,
                "document_id": document_id,
                "title": title,
                "page": page,
                "created_at": created_at,
                "url": url,
            },
        )

    def search(
        self,
        query: str,
        *,
        client_id: str,
        top_k: int = 5,
    ) -> List[RetrievedItem]:
        """Client-scoped search — enforces that only this client's docs match."""
        return self._retriever.search(
            query,
            top_k=top_k,
            client_id=client_id,
            source_type="client_document",
        )

    def clear(self) -> None:
        self._retriever.clear()


_store: "ClientDocumentStore | None" = None


def get_document_store() -> "ClientDocumentStore":
    global _store
    if _store is None:
        _store = ClientDocumentStore()
    return _store
