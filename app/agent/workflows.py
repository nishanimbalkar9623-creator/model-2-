"""AI Workflow Templates — reusable CA workflows.

A workflow is a structured sequence of tool calls with defined inputs/outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowName(str, Enum):
    GST_RECONCILIATION = "gst_reconciliation"
    BANK_CLASSIFICATION = "bank_classification"
    AUDIT_DOCUMENT_CHECK = "audit_document_check"
    ITR_DOCUMENT_CHECK = "itr_document_check"
    MONTHLY_CLOSING = "monthly_closing"
    CLIENT_DOCUMENT_REQUEST = "client_document_request"
    CLIENT_STATUS_REVIEW = "client_status_review"


@dataclass
class WorkflowStep:
    name: str
    tool: str
    description: str
    args_template: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    required: bool = True
    output_key: Optional[str] = None


@dataclass
class WorkflowTemplate:
    name: WorkflowName
    description: str
    required_inputs: List[str] = field(default_factory=list)
    steps: List[WorkflowStep] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    output_format: str = "summary"


# ---- Built-in workflow templates ----

GST_RECONCILIATION_WORKFLOW = WorkflowTemplate(
    name=WorkflowName.GST_RECONCILIATION,
    description="Run GST reconciliation and explain results",
    required_inputs=["client_id", "period"],
    steps=[
        WorkflowStep(
            name="get_recon_summary",
            tool="get_reconciliation_summary",
            description="Get overall reconciliation status",
            args_template={"client_id": "{client_id}", "period": "{period}"},
            output_key="summary",
        ),
        WorkflowStep(
            name="get_exceptions",
            tool="get_reconciliation_exceptions",
            description="Get detailed mismatches/exceptions",
            args_template={"client_id": "{client_id}", "status": "open"},
            output_key="exceptions",
        ),
    ],
    allowed_tools=[
        "get_reconciliation_summary",
        "get_reconciliation_exceptions",
        "get_unreviewed_bank_transactions",
        "process_bank_statement",
        "run_gst_reconciliation",
    ],
    output_format="reconciliation_report",
)

BANK_CLASSIFICATION_WORKFLOW = WorkflowTemplate(
    name=WorkflowName.BANK_CLASSIFICATION,
    description="Process bank statement and identify review items",
    required_inputs=["client_id"],
    steps=[
        WorkflowStep(
            name="get_unreviewed",
            tool="get_unreviewed_bank_transactions",
            description="Get transactions needing review",
            args_template={"client_id": "{client_id}", "limit": 100},
            output_key="unreviewed",
        ),
        WorkflowStep(
            name="process_statement",
            tool="process_bank_statement",
            description="Process uploaded bank statement",
            args_template={"client_id": "{client_id}"},
            required=False,
            output_key="processing_result",
        ),
    ],
    allowed_tools=[
        "get_unreviewed_bank_transactions",
        "process_bank_statement",
        "get_client_documents",
    ],
    output_format="bank_review_report",
)

AUDIT_DOCUMENT_CHECK_WORKFLOW = WorkflowTemplate(
    name=WorkflowName.AUDIT_DOCUMENT_CHECK,
    description="Check audit document completeness",
    required_inputs=["client_id"],
    steps=[
        WorkflowStep(
            name="get_documents",
            tool="get_client_documents",
            description="List all client documents",
            args_template={"client_id": "{client_id}", "doc_type": "audit"},
            output_key="documents",
        ),
        WorkflowStep(
            name="get_requests",
            tool="get_client_requests",
            description="Check for pending document requests",
            args_template={"client_id": "{client_id}", "status": "open"},
            output_key="requests",
        ),
    ],
    allowed_tools=["get_client_documents", "get_client_requests", "create_client_request"],
    output_format="document_checklist",
)

ITR_DOCUMENT_CHECK_WORKFLOW = WorkflowTemplate(
    name=WorkflowName.ITR_DOCUMENT_CHECK,
    description="Check ITR filing document readiness",
    required_inputs=["client_id", "financial_year"],
    steps=[
        WorkflowStep(
            name="get_documents",
            tool="get_client_documents",
            description="List ITR-relevant documents",
            args_template={"client_id": "{client_id}", "doc_type": "itr"},
            output_key="documents",
        ),
        WorkflowStep(
            name="get_pending",
            tool="get_pending_work",
            description="Check pending ITR tasks",
            args_template={"client_id": "{client_id}"},
            output_key="pending",
        ),
    ],
    allowed_tools=["get_client_documents", "get_pending_work", "get_upcoming_deadlines"],
    output_format="itr_checklist",
)

MONTHLY_CLIENT_REVIEW_WORKFLOW = WorkflowTemplate(
    name=WorkflowName.MONTHLY_CLOSING,
    description="Comprehensive monthly client review",
    required_inputs=["client_id"],
    steps=[
        WorkflowStep(
            name="status",
            tool="get_client_status",
            description="Current client status",
            args_template={"client_id": "{client_id}"},
            output_key="status",
        ),
        WorkflowStep(
            name="pending",
            tool="get_pending_work",
            description="All pending work items",
            args_template={"client_id": "{client_id}"},
            output_key="pending",
        ),
        WorkflowStep(
            name="deadlines",
            tool="get_upcoming_deadlines",
            description="Upcoming compliance deadlines",
            args_template={"client_id": "{client_id}", "days_ahead": 30},
            output_key="deadlines",
        ),
        WorkflowStep(
            name="documents",
            tool="get_client_documents",
            description="Recent documents",
            args_template={"client_id": "{client_id}", "limit": 20},
            output_key="documents",
        ),
        WorkflowStep(
            name="requests",
            tool="get_client_requests",
            description="Open client requests",
            args_template={"client_id": "{client_id}", "status": "open"},
            output_key="requests",
        ),
        WorkflowStep(
            name="recon",
            tool="get_reconciliation_summary",
            description="GST reconciliation status",
            args_template={"client_id": "{client_id}"},
            required=False,
            output_key="reconciliation",
        ),
    ],
    allowed_tools=[
        "get_client_status",
        "get_pending_work",
        "get_upcoming_deadlines",
        "get_client_documents",
        "get_client_requests",
        "get_reconciliation_summary",
        "get_client_meetings",
    ],
    output_format="monthly_review",
)

CLIENT_DOCUMENT_REQUEST_WORKFLOW = WorkflowTemplate(
    name=WorkflowName.CLIENT_DOCUMENT_REQUEST,
    description="Create structured document request for client",
    required_inputs=["client_id", "documents_needed"],
    steps=[
        WorkflowStep(
            name="create_request",
            tool="create_client_request",
            description="Create client request for documents",
            args_template={"client_id": "{client_id}", "subject": "{documents_needed}"},
            output_key="request",
        ),
    ],
    allowed_tools=["create_client_request", "get_client_documents"],
    output_format="request_confirmation",
)

CLIENT_STATUS_REVIEW_WORKFLOW = WorkflowTemplate(
    name=WorkflowName.CLIENT_STATUS_REVIEW,
    description="Quick client status overview",
    required_inputs=["client_id"],
    steps=[
        WorkflowStep(
            name="status",
            tool="get_client_status",
            description="Current status",
            args_template={"client_id": "{client_id}"},
            output_key="status",
        ),
        WorkflowStep(
            name="pending",
            tool="get_pending_work",
            description="Pending items",
            args_template={"client_id": "{client_id}"},
            output_key="pending",
        ),
        WorkflowStep(
            name="meetings",
            tool="get_client_meetings",
            description="Upcoming meetings",
            args_template={"client_id": "{client_id}"},
            required=False,
            output_key="meetings",
        ),
    ],
    allowed_tools=["get_client_status", "get_pending_work", "get_client_meetings"],
    output_format="status_summary",
)


WORKFLOW_REGISTRY: Dict[WorkflowName, WorkflowTemplate] = {
    WorkflowName.GST_RECONCILIATION: GST_RECONCILIATION_WORKFLOW,
    WorkflowName.BANK_CLASSIFICATION: BANK_CLASSIFICATION_WORKFLOW,
    WorkflowName.AUDIT_DOCUMENT_CHECK: AUDIT_DOCUMENT_CHECK_WORKFLOW,
    WorkflowName.ITR_DOCUMENT_CHECK: ITR_DOCUMENT_CHECK_WORKFLOW,
    WorkflowName.MONTHLY_CLOSING: MONTHLY_CLIENT_REVIEW_WORKFLOW,
    WorkflowName.CLIENT_DOCUMENT_REQUEST: CLIENT_DOCUMENT_REQUEST_WORKFLOW,
    WorkflowName.CLIENT_STATUS_REVIEW: CLIENT_STATUS_REVIEW_WORKFLOW,
}


def get_workflow(name: WorkflowName) -> Optional[WorkflowTemplate]:
    return WORKFLOW_REGISTRY.get(name)


def list_workflows() -> List[WorkflowTemplate]:
    return list(WORKFLOW_REGISTRY.values())


def match_workflow(message: str, client_id: Optional[str] = None) -> Optional[WorkflowName]:
    """Simple intent matching for workflow selection.
    
    Only matches action-oriented requests, not informational questions.
    """
    msg = message.lower()
    
    # Action verbs that indicate workflow execution
    action_verbs = ["run", "execute", "start", "perform", "do", "trigger", "initiate", "launch"]
    has_action_verb = any(v in msg for v in action_verbs)
    
    # GST reconciliation - only for action requests
    if has_action_verb and any(w in msg for w in ["gst reconciliation", "reconcile gst", "gst mismatch"]):
        return WorkflowName.GST_RECONCILIATION
    
    # Bank classification - only for action requests
    if has_action_verb and any(w in msg for w in ["bank statement", "process bank", "bank transaction", "bank review"]):
        return WorkflowName.BANK_CLASSIFICATION
    
    # Audit document check - action or explicit check request
    if any(w in msg for w in ["check audit document", "audit checklist", "verify audit file", "audit document check"]):
        return WorkflowName.AUDIT_DOCUMENT_CHECK
    
    # ITR document check
    if any(w in msg for w in ["check itr document", "itr checklist", "verify tax document", "itr document check"]):
        return WorkflowName.ITR_DOCUMENT_CHECK
    
    # Monthly closing
    if has_action_verb and any(w in msg for w in ["monthly review", "month end", "monthly closing", "client review"]):
        return WorkflowName.MONTHLY_CLOSING
    
    # Document request - action oriented
    if has_action_verb and any(w in msg for w in ["request document", "ask for document", "missing document"]):
        return WorkflowName.CLIENT_DOCUMENT_REQUEST
    
    # Status review - question or action
    if any(w in msg for w in ["client status", "what is pending", "status review", "overview", "status summary"]):
        return WorkflowName.CLIENT_STATUS_REVIEW
    
    return None