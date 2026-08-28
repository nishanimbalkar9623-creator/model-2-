"""Configurable backend endpoint mapping.

Allows the AI Engine to work with different backend API structures
without code changes. Configured via environment variables.
"""

from __future__ import annotations

from typing import Dict, Optional

from app.config import settings


# Default endpoint map - can be overridden via environment
DEFAULT_ENDPOINT_MAP: Dict[str, str] = {
    # Client endpoints
    "list_clients": "/api/v1/ai-tools/list_clients",
    "get_client": "/api/v1/ai-tools/get_client",
    "get_client_services": "/api/v1/ai-tools/get_client_services",
    "get_client_status": "/api/v1/ai-tools/get_client_status",
    "get_client_activities": "/api/v1/ai-tools/get_client_activities",
    "get_client_meetings": "/api/v1/ai-tools/get_client_meetings",
    
    # Document endpoints
    "get_client_documents": "/api/v1/ai-tools/get_client_documents",
    "search_client_documents": "/api/v1/ai-tools/search_client_documents",
    
    # Work/Task endpoints
    "get_pending_work": "/api/v1/ai-tools/get_pending_work",
    "get_upcoming_deadlines": "/api/v1/ai-tools/get_upcoming_deadlines",
    "get_client_requests": "/api/v1/ai-tools/get_client_requests",
    "create_client_request": "/api/v1/ai-tools/create_client_request",
    "create_task": "/api/v1/ai-tools/create_task",
    "update_task": "/api/v1/ai-tools/update_task",
    "search_tasks": "/api/v1/ai-tools/search_tasks",
    
    # Meeting endpoints
    "create_meeting": "/api/v1/ai-tools/create_meeting",
    "update_meeting": "/api/v1/ai-tools/update_meeting",
    
    # Reconciliation endpoints
    "get_reconciliation_summary": "/api/v1/ai-tools/get_reconciliation_summary",
    "get_reconciliation_exceptions": "/api/v1/ai-tools/get_reconciliation_exceptions",
    "get_unreviewed_bank_transactions": "/api/v1/ai-tools/get_unreviewed_bank_transactions",
    "process_bank_statement": "/api/v1/ai-tools/process_bank_statement",
    "run_gst_reconciliation": "/api/v1/ai-tools/run_gst_reconciliation",
    
    # Report/Export endpoints
    "generate_client_report": "/api/v1/ai-tools/generate_client_report",
    "generate_tally_export": "/api/v1/ai-tools/generate_tally_export",
}

# Allow environment variable overrides
# Format: BACKEND_ENDPOINT_<TOOL_NAME>=/custom/path
def load_endpoint_map() -> Dict[str, str]:
    """Load endpoint map from environment, falling back to defaults."""
    endpoint_map = DEFAULT_ENDPOINT_MAP.copy()
    
    # Check for environment variable overrides
    import os
    for key, value in os.environ.items():
        if key.startswith("BACKEND_ENDPOINT_"):
            tool_name = key[len("BACKEND_ENDPOINT_"):].lower()
            if tool_name in endpoint_map:
                endpoint_map[tool_name] = value
    
    return endpoint_map


ENDPOINT_MAP = load_endpoint_map()


def get_endpoint(tool_name: str) -> str:
    """Get the backend endpoint for a tool."""
    return ENDPOINT_MAP.get(tool_name, f"/api/v1/ai-tools/{tool_name}")


def get_all_endpoints() -> Dict[str, str]:
    """Return the full endpoint map."""
    return ENDPOINT_MAP.copy()