"""CA knowledge base.

Embeds reusable CA knowledge content (GST, income tax, compliance, etc.)
into a knowledge-only retriever whose metadata is always
``source_type="knowledge"`` and never carries a client_id.
"""

from __future__ import annotations

from typing import Dict, List

from app.rag.embeddings import EmbeddingProvider, create_embedding_provider
from app.rag.retriever import RetrievedItem, Retriever


class CAKnowledgeBase:
    def __init__(self, provider: Optional[EmbeddingProvider] = None):
        self._retriever = Retriever(provider or create_embedding_provider())
        self._seed()

    def _seed(self) -> None:
        seed_content: List[Dict[str, str]] = [
            {
                "title": "GST Reconciliation",
                "body": (
                    "GST reconciliation compares the sales/purchase data reported in the "
                    "GSTR-2B (auto-drafted supplier statements) with the books of accounts "
                    "(ledgers) to identify mismatches in turnover, ITC claims and tax paid. "
                    "Common mismatch causes include invoice date differences, missing HSN codes, "
                    "duplicate entries, and goods-in-transit timing. It helps validate Input Tax "
                    "Credit (ITC) and avoid notices."
                ),
            },
            {
                "title": "GSTR-2B",
                "body": (
                    "GSTR-2B is a monthly auto-populated statement in the view-only GSTR-2A/2B "
                    "module reflecting supplier-reported supplies, and eligible ITC. It is not a "
                    "return to be filed but a reference for reconciling ITC."
                ),
            },
            {
                "title": "Input Tax Credit (ITC)",
                "body": (
                    "ITC is the credit a registered person can claim for GST paid on purchases, "
                    "subject to conditions: the recipient has the invoice and proof of receipt of "
                    "goods/services, the tax has been paid by the supplier, and the return is "
                    "furnished. Section 16 of CGST Act governs ITC eligibility."
                ),
            },
            {
                "title": "Tally Export",
                "body": (
                    "Tally export in the AOS context packages reconciled client data (journal "
                    "entries, ledgers) into a Tally-compatible format (XML/CSV) for import into "
                    "Tally ERP/Prime. It is only performed when the backend confirms a successful "
                    "export event."
                ),
            },
            {
                "title": "Compliance Deadlines",
                "body": (
                    "Key monthly/quarterly/annual deadlines include GST return filing (GSTR-1, "
                    "GSTR-3B), TDS returns (24Q/26Q), advance tax installments, and annual return "
                    "(GSTR-9). Dates vary by turnover threshold and period; the backend owns the "
                    "authoritative deadline calendar."
                ),
            },
            {
                "title": "Advance Tax",
                "body": (
                    "Advance tax is income tax payable in installments during the financial year "
                    "when estimated tax liability exceeds Rs. 10,000. Due dates are generally 15 "
                    "Jun, 15 Sep, 15 Dec, and 15 Mar under Section 211 of the Income Tax Act."
                ),
            },
        ]
        for item in seed_content:
            self._retriever.add(
                item["body"],
                {
                    "source_type": "knowledge",
                    "title": item["title"],
                    # NOTE: no client_id — knowledge is global and never client-scoped
                },
            )

    def query(self, question: str, top_k: int = 3) -> List[RetrievedItem]:
        return self._retriever.search(
            question, top_k=top_k, source_type="knowledge", client_id=None
        )


_kb: "CAKnowledgeBase | None" = None


def get_knowledge_base() -> "CAKnowledgeBase":
    global _kb
    if _kb is None:
        _kb = CAKnowledgeBase()
    return _kb
