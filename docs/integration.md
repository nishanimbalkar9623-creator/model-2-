# AOS AI Engine — Integration Contract

This document describes how the **Frontend** and **Backend** repositories
communicate with the **AI Engine** repository, and the HTTP contract the
engine expects from the Backend.

## Repositories

| Repo        | Role                                                             |
|-------------|------------------------------------------------------------------|
| Frontend    | UI / Dashboard / Clients / Documents / Tracker / AI Chat / Voice |
| Backend + ML| FastAPI business backend, PostgreSQL, client data, ML, storage    |
| AI Engine   | This repo — agent orchestration, tool calling, memory, RAG, STT   |

The AI Engine never talks to the database directly. All data and business
actions flow through authenticated HTTP to the Backend, which remains the
authority for identity, permissions, and business truth.

## Frontend → AI Engine

The Frontend calls the AI Engine for chat, streaming, voice, and confirms.

- `POST /api/v1/chat`
- `POST /api/v1/chat/stream` (SSE — tokens + tool events)
- `POST /api/v1/chat/confirm`
- `POST /api/v1/voice/transcribe`
- `POST /api/v1/voice/chat` (voice → STT → agent → response)
- `GET /health`, `GET /ready`

The Frontend should use the `conversation_id` from a chat response for
follow-ups. For client-scoped questions it may pass `client_id`, and it may
pass `user_id` / `user_role` so the engine can apply its safety boundary.
**The engine does not trust the frontend for authorization** — it forwards
identity to the Backend, which authorizes each call.

### Request/Response Schemas

#### Chat Request
```json
{
  "message": "What is pending for ABC?",
  "client_id": "optional",
  "conversation_id": "optional",
  "user_id": "optional",
  "user_role": "optional"
}
```

#### Chat Response
```json
{
  "conversation_id": "conv_...",
  "message": "...",
  "tool_calls": [
    {"name": "get_pending_work", "arguments": {...}, "status": "ok", "result": {...}, "error": null}
  ],
  "requires_confirmation": false,
  "pending_confirmation": null,
  "pending_confirmation_args": {},
  "sources": [
    {"source_type": "backend", "client_id": "abc", "title": "Pending Work"}
  ],
  "request_id": "req_..."
}
```

#### Streaming Events (SSE)
```
event: start
data: {"state": "thinking"}

event: thinking
data: {"iteration": 1}

event: tool_started
data: {"tool": "get_reconciliation_summary", "arguments": {"client_id": "abc"}}

event: tool_completed
data: {"tool": "get_reconciliation_summary", "status": "ok", "result": "..."}

event: token
data: {"content": "Reconciliation summary: "}

event: token
data: {"content": "8,742 matched..."}

event: done
data: {"conversation_id": "conv_...", "requires_confirmation": false, "tool_calls": [...]}
```

#### Voice Transcribe Request
```
POST /api/v1/voice/transcribe
Content-Type: multipart/form-data

file: <audio bytes>
language: "en" (optional)
```

#### Voice Transcribe Response
```json
{
  "text": "What is pending for ABC?",
  "language": "en",
  "confidence": 0.95,
  "provider": "openai-whisper",
  "duration_seconds": 3.2
}
```

#### Voice Chat Request
```
POST /api/v1/voice/chat
Content-Type: multipart/form-data

file: <audio bytes>
language: "en" (optional)
client_id: "abc" (optional)
conversation_id: "conv_..." (optional)
user_id: "user1" (optional)
user_role: "associate" (optional)
```

#### Voice Chat Response
```json
{
  "transcription": {
    "text": "What is pending for ABC?",
    "language": "en",
    "confidence": 0.95
  },
  "response": { ...ChatResponse... }
}
```

#### Confirm Request
```json
{
  "conversation_id": "conv_...",
  "decision": true
}
```

#### Confirm Response
```json
{
  "conversation_id": "conv_...",
  "message": "Action 'create_meeting' completed successfully.",
  "tool_results": [...]
}
```

## AI Engine → Backend

The engine calls the Backend over HTTP. Auth is an API key or JWT configured
in `.env` (`BACKEND_API_KEY` / `BACKEND_JWT_TOKEN`). Identity
(`user_id`, `user_role`) is forwarded in headers so the Backend can enforce
per-client authorization and return `403` when a user is not allowed.

### Tool invocation

Each registered tool maps to a backend endpoint:

```
POST /api/v1/ai-tools/<tool_name>
Content-Type: application/json
X-User-Id / X-User-Role (forwarded identity)
Authorization: Bearer <service or user token>

{ ...validated Pydantic arguments... }
```

### Endpoint Override

Backend endpoints can be overridden via environment variables:
```
BACKEND_ENDPOINT_GET_CLIENT_STATUS=/custom/v1/clients/{client_id}/status
BACKEND_ENDPOINT_CREATE_MEETING=/custom/v1/meetings
...
```

See `app/backend/endpoints.py` for the full default map.

### Expected status codes

| Code | Meaning                              | Engine handling      |
|------|--------------------------------------|----------------------|
| 200  | Success                              | use payload          |
| 400 / 422 | Validation error               | `BackendValidationError` |
| 401  | Unauthenticated — bad/missing token  | `BackendAuthError`   |
| 403  | Authorized calls only — not permitted| `BackendPermissionError` → tool BLOCKED |
| 404  | Resource not found                   | `BackendNotFoundError` |
| 409  | Conflict (e.g. duplicate)            | `BackendConflictError` |
| 429  | Rate limited                         | `BackendRateLimitedError` |
| 5xx  | Backend error                        | `BackendServerError` |

GET requests are retried (`BACKEND_MAX_RETRIES`); mutation requests are never
automatically retried.

### Required Backend Endpoints

The AI Engine expects the Backend to implement these `/api/v1/ai-tools/*` endpoints:

| Tool | HTTP Method | Expected Response |
|------|-------------|-------------------|
| `list_clients` | GET | `{ "items": [Client, ...] }` |
| `get_client` | POST | `Client` |
| `get_client_services` | POST | `ClientServiceConfig` |
| `get_client_status` | POST | `ClientStatus` |
| `get_client_activities` | POST | `{ "items": [Activity, ...] }` |
| `get_client_meetings` | POST | `{ "items": [Meeting, ...] }` |
| `get_client_documents` | POST | `{ "items": [Document, ...] }` |
| `search_client_documents` | POST | `{ "items": [Document, ...] }` |
| `get_pending_work` | POST | `{ "items": [PendingItem, ...] }` |
| `get_upcoming_deadlines` | POST | `{ "items": [Deadline, ...] }` |
| `get_client_requests` | POST | `{ "items": [ClientRequest, ...] }` |
| `create_client_request` | POST | `ClientRequest` |
| `create_task` | POST | `Task` |
| `update_task` | PATCH | `Task` |
| `search_tasks` | POST | `{ "items": [Task, ...] }` |
| `create_meeting` | POST | `Meeting` |
| `update_meeting` | PATCH | `Meeting` |
| `get_reconciliation_summary` | POST | `ReconciliationSummary` |
| `get_reconciliation_exceptions` | POST | `{ "items": [ReconciliationException, ...] }` |
| `get_unreviewed_bank_transactions` | POST | `{ "items": [BankTransaction, ...] }` |
| `process_bank_statement` | POST | `ProcessingResult` |
| `run_gst_reconciliation` | POST | `ReconciliationSummary` |
| `generate_client_report` | POST | `ReportResult` |
| `generate_tally_export` | POST | `ExportResult` |

Payload shapes must match `app/backend/schemas.py` models.

### Payload shapes

The engine parses backend responses into the models in
`app/backend/schemas.py` (`Client`, `ClientStatus`, `Activity`, `Document`,
`PendingItem`, `Deadline`, `ReconciliationSummary`, `ReconciliationException`,
`BankTransaction`, `ClientRequest`, ...). The Backend repo should align its
`/api/v1/ai-tools/*` responses with those shapes.

## Sample chat exchanges

### Client query
```
User:     "What is pending for ABC?"
Engine:   classify -> client_specific
          plan     -> [get_client_status, get_pending_work]
          backend  -> POST /api/v1/ai-tools/get_pending_work {client_id: ...}
          reply    -> "Pending for ABC: ..."  + sources
```

### GST reconciliation workflow
```
User:     "Run GST reconciliation for ABC"
Engine:   detect workflow -> gst_reconciliation
          execute steps -> [get_reconciliation_summary, get_reconciliation_exceptions]
          reply    -> Formatted table with matched/missing/mismatches
```

### Action with confirmation
```
User:     "Run GST reconciliation for ABC"
Engine:   classify -> action
          gate     -> create_confirmation_gate(...)  [needs_confirmation]
          reply    -> "I'll need your confirmation before running GST reconciliation."

User:     (confirm via /api/v1/chat/confirm)
Engine:   backend  -> POST /api/v1/ai-tools/run_gst_reconciliation {client_id}
          reply    -> "GST reconciliation started. Job ID: ..."
```

### Proactive priorities
```
User:     "What should I do today?"
Engine:   aggregate -> [gst_mismatches, bank_pending, deadlines, tasks, requests]
          reply    -> Ranked priority list with emojis
```

## Client context & isolation

The engine builds a `ClientContext` (client_id, name, financial_year,
selected_services, industry, current_period, user_id, user_role) from backend
data. A user cannot inject arbitrary client scope by typing it. Per-client
tool calls are checked against the caller's allowed clients, and the Backend
independently enforces the final authorization (403).

**Service-aware responses:** The AI adapts its focus based on `selected_services`:
- GST + Accounting → reconciliation, bank processing, tasks, deadlines
- Audit → audit tasks, findings, documents
- Taxation → ITR workflow, tax deadlines

## Environment variables

See `.env.example`. Minimum for a working deployment:

```
LLM_PROVIDER=mock          # or openai | gemini | anthropic | ollama
BACKEND_BASE_URL=http://backend:8000
BACKEND_API_KEY=...
ENGINE_API_KEY=...         # used to authenticate frontend -> engine
```

### Backend endpoint overrides
```
BACKEND_ENDPOINT_LIST_CLIENTS=/api/v1/clients
BACKEND_ENDPOINT_GET_CLIENT=/api/v1/clients/{client_id}
...
```

## Voice

The Frontend sends audio to `POST /api/v1/voice/transcribe` and receives
`{ "text", "language", "confidence" }`. The engine uses the configured
`STT_PROVIDER` (mock by default for development).

### Voice Chat (integrated)

`POST /api/v1/voice/chat` accepts audio, transcribes it, and runs the full
agent pipeline. Returns both transcription and agent response in one call.
Uses the same agent logic as text chat — no separate business logic path.

## Graceful Degradation

| Failure | Behavior |
|---------|----------|
| LLM unavailable | Falls back to `MockLLMProvider`, returns deterministic responses |
| Backend unavailable | Returns safe error messages, no hallucinated data |
| STT unavailable | `/voice/transcribe` returns error, `/voice/chat` fails gracefully |
| RAG unavailable | Knowledge queries return empty, clearly indicated |

The `GracefulDegradation` manager tracks service health. Frontend can check
degradation status via response metadata.