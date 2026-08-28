"""Tests for RAG metadata filtering and client-data isolation."""

from __future__ import annotations

from app.rag.document_search import ClientDocumentStore
from app.rag.knowledge import CAKnowledgeBase


def test_knowledge_no_client_scope():
    kb = CAKnowledgeBase()
    hits = kb.query("What is GST reconciliation?", top_k=1)
    assert hits
    # knowledge items never carry a client_id
    for h in hits:
        assert h.metadata.get("source_type") == "knowledge"
        assert "client_id" not in h.metadata


def test_client_document_store_isolation():
    store = ClientDocumentStore()
    store.index_chunk(
        content="ABC 2024 GST return total",
        client_id="abc",
        document_id="d1",
        title="ABC GSTR-3B",
    )
    store.index_chunk(
        content="XYZ confidential bank balance",
        client_id="xyz",
        document_id="d2",
        title="XYZ Bank",
    )
    # Search for ABC returns only ABC docs
    abc_hits = store.search("ABC GST return", client_id="abc", top_k=5)
    for h in abc_hits:
        assert h.metadata["client_id"] == "abc"

    xyz_hits = store.search("ABC GST return", client_id="xyz", top_k=5)
    for h in xyz_hits:
        assert h.metadata["client_id"] == "xyz"


def test_metadata_filtering_source_type():
    store = ClientDocumentStore()
    store.index_chunk(content="a", client_id="abc", document_id="d1", title="t1")
    from app.rag.retriever import Retriever
    from app.rag.embeddings import MockEmbeddingProvider

    r = Retriever(MockEmbeddingProvider())
    r.add("global knowledge", {"source_type": "knowledge"})
    r.add("client doc", {"source_type": "client_document", "client_id": "abc", "document_id": "d1"})

    k = r.search("doc", source_type="client_document", client_id="abc")
    assert all(x.metadata.get("source_type") == "client_document" for x in k)
