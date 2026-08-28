# AOS AI Engine — Tools

Every tool is declared in `app/tools/registry.py` and grouped by domain in
`app/tools/*_tools.py`. A tool carries:

- `name` — unique identifier used by the LLM and by `POST /api/v1/ai-tools/<name>`.
- `description` — what it does (tells the LLM when to use it).
- `input_model` — a Pydantic schema; every argument is validated against it.
- `kind` — `read` or `action`.
- `permission` — `view` / `manage` / `admin` (role-gated).
- `requires_confirmation` — whether the action needs explicit confirmation.
- `destructive` — whether it is a high-risk/destructive operation.

Execution always goes through the Backend (`BackendClient`) — the engine never
implements business logic itself.

## Registered tools (24)

### Read tools

| Tool                              | Purpose                                       |
|-----------------------------------|-----------------------------------------------|
| `list_clients`                    | Clients the caller may view                    |
| `get_client`                      | Client identity / org details                  |
| `get_client_services`             | Service configuration (GST, TDS, books, ...)   |
| `get_client_status`               | Current work status / state of a client        |
| `get_client_activities`           | Recent activities / audit trail                |
| `get_client_meetings`             | Upcoming/past meetings for a client            |
| `get_client_documents`            | Client document list                           |
| `search_client_documents`         | Search within a client's documents             |
| `get_pending_work`                | Pending tasks/items for a client               |
| `get_upcoming_deadlines`          | Upcoming compliance deadlines                  |
| `get_client_requests`             | Client requests list                           |
| `get_reconciliation_summary`      | Recon summary for a client (GST, bank, ...)    |
| `get_reconciliation_exceptions`   | Recon mismatch / exception list                |
| `get_unreviewed_bank_transactions`| Unreviewed bank transactions                   |
| `search_tasks`                    | Search a client's tasks                        |

### Action tools

| Tool                     | Purpose                                | Confirmation |
|--------------------------|----------------------------------------|--------------|
| `create_task`            | Create a task                          | conditional  |
| `update_task`            | Update a task                          | conditional  |
| `create_meeting`         | Schedule a meeting                      | conditional  |
| `update_meeting`         | Update/reschedule a meeting            | conditional  |
| `create_client_request`  | Raise a client request                  | conditional  |
| `generate_client_report` | Generate a report for a client         | conditional  |
| `run_gst_reconciliation` | Run GST reconciliation                 | always       |
| `process_bank_statement` | Process a bank statement               | conditional  |
| `generate_tally_export`  | Generate Tally-compatible export       | always       |

## Workflow Templates

| Workflow | Description | Required Inputs | Steps |
|----------|-------------|-----------------|-------|
| `gst_reconciliation` | Run GST reconciliation and explain results | client_id, period | summary → exceptions |
| `bank_classification` | Process bank statement and identify review items | client_id | unreviewed → process |
| `audit_document_check` | Check audit document completeness | client_id | documents → requests |
| `itr_document_check` | Check ITR filing document readiness | client_id, financial_year | documents → pending |
| `monthly_closing` | Comprehensive monthly client review | client_id | status, pending, deadlines, docs, requests, recon |
| `client_document_request` | Create structured document request for client | client_id, documents_needed | create_request |
| `client_status_review` | Quick client status overview | client_id | status, pending, meetings |

## Execution rules

- **Read** tools may fire automatically when authorized.
- **Mutating** tools are gated: the executor records a pending action in
  conversation memory and the user must confirm via `/api/v1/chat/confirm`.
- **High-impact** actions (`run_gst_reconciliation`, `generate_tally_export`)
  always require confirmation (see `app/safety/action_policy.py`).
- The LLM can never invent tool arguments — Pydantic validation rejects or
  coerces invalid input.
- Destructive deletion is outside the supported tool policy and is rejected.

## Safety checks (executor order)

1. Permission check (`check_tool_allowed`).
2. Client isolation (`assert_client_access`).
3. Pydantic argument validation.
4. Confirmation gate for mutating/high-risk tools
   (`requires_confirmation` + `create_confirmation_gate`) → `needs_confirmation`.
5. Execution through the Backend.
6. Backend error → AI-safe result (403 → blocked, others → sanitized error).

Tool calls are logged in sanitized form (PII / secrets redacted).

## Tool Argument Schemas

### `create_task`
```json
{
  "client_id": "string (optional)",
  "title": "string (required, 2-200 chars)",
  "description": "string (optional, max 1000)",
  "due": "ISO datetime (optional)",
  "assignee": "user_id (optional)",
  "priority": "low|medium|high|urgent (default: medium)"
}
```

### `create_meeting`
```json
{
  "client_id": "string (optional)",
  "title": "string (required, 2-200 chars)",
  "scheduled_at": "ISO datetime (required)",
  "duration_minutes": "integer (5-480, default: 60)",
  "attendees": "string[] (optional)"
}
```

### `generate_client_report`
```json
{
  "client_id": "string (required)",
  "report_type": "string (e.g. monthly-work-summary, reconciliation-report)",
  "period": "string (e.g. FY2024-25, Aug-2025)",
  "include_ai_generated": "boolean (default: true)"
}
```

### `run_gst_reconciliation`
```json
{
  "client_id": "string (required)",
  "period": "string (optional)"
}
```

### `process_bank_statement`
```json
{
  "client_id": "string (required)",
  "document_id": "string (optional)"
}
```

### `generate_tally_export`
```json
{
  "client_id": "string (required)",
  "financial_year": "string (required, e.g. FY2024-25)"
}
```

### `get_reconciliation_exceptions`
```json
{
  "client_id": "string (required)",
  "status": "open|matched (optional)"
}
```

### `get_unreviewed_bank_transactions`
```json
{
  "client_id": "string (required)",
  "limit": "integer (1-200, default: 50)"
}
```

### `search_client_documents`
```json
{
  "client_id": "string (required)",
  "query": "string (required)",
  "top_k": "integer (1-20, default: 5)"
}
```

### `get_upcoming_deadlines`
```json
{
  "days_ahead": "integer (1-365, default: 30)",
  "client_id": "string (optional)"
}
```

### `create_client_request`
```json
{
  "client_id": "string (required)",
  "subject": "string (3-200 chars, required)",
  "description": "string (optional)"
}
```