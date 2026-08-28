# AOS AI Engine

The **AI Engine** for **AOS — Accounting Operating System**, an AI-powered
operating platform for Chartered Accountants.

This repository holds the **AI Copilot / agent orchestration** layer only.
It does **not** contain the frontend, the business backend, or the database.

```
FRONTEND REPO        BACKEND + ML REPO        THIS REPO (AI ENGINE)
[UI / Dashboard]  -> [FastAPI + PostgreSQL] -> [AI Copilot / Agent]
                                      ^              |
                                      +---- HTTP ----+
```

The AI Engine talks to the **Backend** over authenticated HTTP APIs and never
touches the database directly. The Backend remains the authority for
permissions, client data, and business logic.

---

## What it does

A CA interacts with AOS in natural language (and eventually voice). The engine:

1. Answers general CA/accounting questions.
2. Answers client-specific questions using backend-provided data.
3. Searches authorized client documents.
4. Summarizes client history, status, and reconciliation results.
5. Suggests next actions.
6. Creates/updates tasks, meetings, and client requests via backend tools.
7. Generates reports and runs reconciliations through backend tools.
8. Maintains conversational context.
9. Accepts voice input (STT).
10. Asks for confirmation before consequential actions.

**Advanced capabilities:**
- **Multi-step workflows** — GST reconciliation, bank classification, audit document checks, monthly closing
- **Service-aware responses** — Adapts to client's enabled services (GST, Audit, Taxation, etc.)
- **Proactive work intelligence** — "What should I do today?" aggregates overdue tasks, deadlines, mismatches
- **Voice chat** — `POST /api/v1/voice/chat` transcribes and runs through agent pipeline
- **Streaming with tool events** — SSE shows `thinking`, `tool_started`, `tool_completed`, `token`
- **Client data isolation** — Strict per-client scope enforcement at every layer
- **Prompt injection defense** — Documents treated as DATA, never instructions

It is an **agent**, not a chatbot — it classifies intent, plans tool calls,
executes them through a safety boundary, and composes grounded responses.

---

## Quickstart

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit values as needed
```

Run with the development **MockLLMProvider** (no external API keys needed):

```bash
export LLM_PROVIDER=mock
uvicorn app.main:app --reload
```

* All config is environment-driven (see `.env.example`). No secrets are
  hardcoded.

---

## Endpoints

| Method | Path                        | Description                       |
|--------|-----------------------------|-----------------------------------|
| GET    | `/health`                   | Liveness probe                    |
| GET    | `/ready`                    | Readiness (backend configured)    |
| POST   | `/api/v1/chat`              | Non-streaming chat                |
| POST   | `/api/v1/chat/stream`       | Server-Sent Events (tokens + tool events) |
| POST   | `/api/v1/chat/confirm`      | Confirm/reject a pending action   |
| POST   | `/api/v1/voice/transcribe`  | Speech-to-text                    |
| POST   | `/api/v1/voice/chat`        | Voice → STT → Agent → Response    |

### Chat request

```json
{
  "message": "What is pending for ABC?",
  "client_id": "optional",
  "conversation_id": "optional",
  "user_id": "optional",
  "user_role": "optional"
}
```

### Chat response

```json
{
  "conversation_id": "conv_...",
  "message": "...",
  "tool_calls": [],
  "requires_confirmation": false,
  "pending_confirmation": null,
  "pending_confirmation_args": {},
  "sources": [],
  "request_id": ""
}
```

### Streaming events

```json
{"event": "start", "data": {"state": "thinking"}}
{"event": "thinking", "data": {"iteration": 1}}
{"event": "tool_started", "data": {"tool": "get_reconciliation_summary", "arguments": {"client_id": "abc"}}}
{"event": "tool_completed", "data": {"tool": "get_reconciliation_summary", "status": "ok", "result": "..."}}
{"event": "token", "data": {"content": "Reconciliation summary: "}}
{"event": "token", "data": {"content": "8,742 matched..."}}
{"event": "done", "data": {"conversation_id": "...", "requires_confirmation": false}}
```

---

## Configuration

See `.env.example` for the full list. Key variables:

- `LLM_PROVIDER` — `mock | openai | gemini | anthropic | ollama`
- `LLM_MODEL`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`,
  `OLLAMA_BASE_URL`
- `BACKEND_BASE_URL`, `BACKEND_API_KEY` / `BACKEND_JWT_TOKEN`
- `RAG_VECTOR_STORE`, `RAG_EMBEDDING_PROVIDER`
- `STT_PROVIDER`
- `BACKEND_ENDPOINT_<TOOL_NAME>` — Override backend endpoints (e.g., `BACKEND_ENDPOINT_GET_CLIENT_STATUS=/custom/path`)

---

## Testing

```bash
LLM_PROVIDER=mock pytest -q
```

All 51 tests run fully offline (Mock LLM + a stubbed BackendClient). No
external LLM or backend is required.

---

## Layout

```
app/
  agent/        orchestration, intent, execution, confirmation, workflows, recommendations
  api/          FastAPI routes (chat, voice, health)
  backend/      BackendClient, auth, schemas, endpoint map
  llm/          provider abstraction + mock/openai/gemini/anthropic/ollama
  memory/       conversation + working context
  rag/          embeddings, retriever, knowledge, document search
  safety/       permissions, validation, PII, action policy
  speech/       STT abstraction
  tools/        tool registry + domain tool groups (23 tools)
  observability logging, metrics, context, middleware
  schemas/      chat, tools, agent
  config.py
  fallbacks.py  graceful degradation
prompts/        system + CA copilot prompts
tests/
docs/
```

---

## Documentation

- [Architecture](docs/architecture.md)
- [Tools & agent capabilities](docs/tools.md)
- [Integration contract with the Backend & Frontend](docs/integration.md)
- [Demo scenarios](docs/demo.md)