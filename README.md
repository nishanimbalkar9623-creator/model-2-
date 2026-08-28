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

- `LLM_PROVIDER` — `mock | openai | gemini | anthropic | ollama | openrouter`
- `LLM_MODEL`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`,
  `OLLAMA_BASE_URL`
- `BACKEND_BASE_URL`, `BACKEND_API_KEY` / `BACKEND_JWT_TOKEN`
- `RAG_VECTOR_STORE`, `RAG_EMBEDDING_PROVIDER`
- `STT_PROVIDER`
- `BACKEND_ENDPOINT_<TOOL_NAME>` — Override backend endpoints (e.g., `BACKEND_ENDPOINT_GET_CLIENT_STATUS=/custom/path`)

---

## Provider configuration

### Local mock mode (offline, no keys)

```bash
export LLM_PROVIDER=mock
uvicorn app.main:app --reload
```

Use this for development and all offline tests. No internet or API key needed.

### OpenRouter setup (production LLM)

OpenRouter is an OpenAI-compatible aggregator. Set `LLM_PROVIDER=openrouter`
and configure a key pool:

```bash
export LLM_PROVIDER=openrouter
export OPENROUTER_MODEL="openai/gpt-4o-mini"
export OPENROUTER_API_KEY_1="sk-or-..."
export OPENROUTER_API_KEY_2="sk-or-..."
uvicorn app.main:app
```

**Multiple keys (key pool):** provide up to five keys via separate variables
`OPENROUTER_API_KEY_1` … `OPENROUTER_API_KEY_5`. Only as many as you set are
used. The engine:

- rotates keys round-robin,
- temporarily disables a key on `429`/`5xx`/timeout (cooldown via
  `OPENROUTER_KEY_COOLDOWN_SECONDS`, default 60s),
- holds out keys that return `401`/`403` (likely invalid),
- never retries on `400` (bad request/model/schema),
- never exceeds `MAX_LLM_RETRIES` or the number of configured keys.

**Model routing** (optional): `OPENROUTER_FAST_MODEL` and
`OPENROUTER_REASONING_MODEL` slots. The agent requests a *capability*
(`fast`/`reasoning`/default); the frontend never picks arbitrary models.
Unconfigured slots fall back to `OPENROUTER_MODEL`.

**Context control:** large tool results and document extracts are truncated
before they reach the model (`app/llm/context.py`), so huge client datasets are
never sent wholesale to the LLM. The backend/ML layer does the heavy lifting.

### Startup validation

If `LLM_PROVIDER=openrouter` and **no** OpenRouter key is configured, the
service fails fast at startup with a clear error. Mock mode needs no key and
never crashes.

---

## Security warning

> **Never commit `.env`.** It is already in `.gitignore`, but do not paste real
> keys into README, docs, configs, or code.

OpenRouter API keys:

- are masked in all logs (`sk-or-1-foo123` → `****123`),
- never appear in responses, exceptions, `/health`, or `/ready`,
- are never sent to the frontend — the browser talks to this AI Engine, which
  talks to OpenRouter.

---

## Testing

```bash
LLM_PROVIDER=mock pytest -q
```

All tests run fully offline (Mock LLM + a stubbed BackendClient). No external
LLM or backend is required.

**OpenRouter unit tests** (`tests/test_openrouter.py`) run offline too — they
mock the HTTP transport, so no keys or network are needed.

**Optional live integration test** (never part of the default suite): set
`RUN_OPENROUTER_INTEGRATION_TESTS=true` and a real `OPENROUTER_API_KEY_N`, then:

```bash
RUN_OPENROUTER_INTEGRATION_TESTS=true LLM_PROVIDER=openrouter pytest -q tests/test_openrouter.py
```

Otherwise the integration test is skipped.

---

## Layout

```
app/
  agent/        orchestration, intent, execution, confirmation, workflows, recommendations
  api/          FastAPI routes (chat, voice, health)
  backend/      BackendClient, auth, schemas, endpoint map
  llm/          provider abstraction + mock/openai/gemini/anthropic/ollama/openrouter, key pool, errors
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