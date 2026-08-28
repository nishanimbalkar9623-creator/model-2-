"""Intent classifier with workflow detection.

Structured intent classification of the user's message. Tries the LLM
first; falls back to keyword-free heuristics so the engine works even with
the MockProvider or a dead LLM.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from app.agent.workflows import WorkflowName, match_workflow
from app.llm.base import LLMProvider, LLMMessage
from app.schemas.agent import IntentType

_ACTION_VERBS = {
    "schedule", "create", "update", "generate", "export", "process",
    "reconcile", "remind", "send", "cancel", "delete", "change",
    "add", "book", "raise", "close",
}

_ANALYSIS_HINTS = ["mismatch", "exception", "why", "difference", "analyse", "analyze"]

_CLIENT_HINTS = ["for abc", "pending for", "status of", "for client", "client abc"]

_REPORT_HINTS = [" generate report", " monthly report", "report for", " work report"]

_PRIORITY_HINTS = ["what should i do", "what do i do", "priorities", "priority", 
                   "what's important", "whats important", "top priority", "focus on",
                   "what needs attention", "overdue", "urgent"]


def classify_intent_text(message: str) -> IntentType:
    low = " " + message.lower() + " "
    # Client-specific takes precedence over general ("what is pending for ABC")
    if any(a in low for a in _CLIENT_HINTS):
        return IntentType.CLIENT_SPECIFIC
    if low.startswith(("what is ", "what are ", "how do ", "how to ")):
        return IntentType.GENERAL
    if any(a in low for a in _ANALYSIS_HINTS):
        return IntentType.DATA_ANALYSIS
    if any(a in low for a in _REPORT_HINTS):
        return IntentType.REPORT
    if any(a in low for a in _PRIORITY_HINTS):
        return IntentType.CLIENT_SPECIFIC  # Will trigger recommendations
    words = set(low.split())
    if words & _ACTION_VERBS:
        return IntentType.ACTION
    return IntentType.GENERAL


async def classify_intent(
    message: str,
    provider: Optional[LLMProvider] = None,
    conversation_turns: Optional[List[Any]] = None,
    client_id: Optional[str] = None,
) -> Tuple[IntentType, Optional[WorkflowName]]:
    """Try LLM first; fall back to heuristics. Also detects workflow."""
    workflow = match_workflow(message, client_id)
    intent = IntentType.UNKNOWN
    
    if provider is not None and getattr(provider, "name", "") != "mock":
        try:
            prompt = (
                "Classify the user intent as one of: "
                "general, client_specific, action, data_analysis, report, unknown\n\n"
                f"User message: {message}\n\nReturn ONLY the label."
            )
            result = await provider.generate([LLMMessage("user", prompt)], temperature=0.0)
            label = result.content.strip().lower()
            label = label.strip("\"'()")
            for it in IntentType:
                if it.value == label:
                    intent = it
                    break
            else:
                intent = classify_intent_text(message)
        except Exception:
            intent = classify_intent_text(message)
    else:
        intent = classify_intent_text(message)
    
    # Workflow detection can override/refine intent
    if workflow:
        if workflow in (WorkflowName.GST_RECONCILIATION, WorkflowName.BANK_CLASSIFICATION):
            intent = IntentType.DATA_ANALYSIS
        elif workflow in (WorkflowName.MONTHLY_CLOSING, WorkflowName.CLIENT_STATUS_REVIEW):
            intent = IntentType.CLIENT_SPECIFIC
        elif workflow in (WorkflowName.CLIENT_DOCUMENT_REQUEST,):
            intent = IntentType.ACTION
        elif workflow in (WorkflowName.AUDIT_DOCUMENT_CHECK, WorkflowName.ITR_DOCUMENT_CHECK):
            intent = IntentType.CLIENT_SPECIFIC
    
    return intent, workflow
