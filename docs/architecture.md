# AOS AI Engine — Architecture

The AI Engine is a single, deployable FastAPI service. It is a **tool-using
agent** layered over a provider-independent LLM abstraction, with a hard
safety boundary between the model and the authoritative Backend.

## High-level flow

```
 client / frontend / voice UI
        |
        v
 POST /api/v1/chat  (or /chat/stream, /confirm, /voice/chat)
        |
        v
 +------------- AgentOrchestrator --------------+
 | 1. resolve conversation + validate input     |
 | 2. classify intent + detect workflow (planner)|
 | 3. enrich ClientContext from backend         |
 | 4. LLM-driven tool planning (or workflow)    |
 | 5. execute tools with safety gates           |
 | 6. iterate: reason → plan → execute          |
 | 7. RAG for general / knowledge questions     |
 | 8. synthesize final answer with citations    |
 | 9. persist memory, record telemetry          |
 +----------------------------------------------+
        |
        |  POST /api/v1/ai-tools/<name>  (authenticated)
        v
   BACKEND (authoritative: data, permissions, business logic)
```

## Module responsibilities

### `app/agent`
- `orchestrator.py` — multi-step agent loop with streaming support
- `planner.py` — intent classification + workflow detection
- `executor.py` — `ToolExecutionPlan`: validates args, enforces permissions/client isolation
- `confirmation.py` — gates mutating actions behind explicit user confirm
- `prompts.py` — system prompt builder with role/client context
- `state.py` — turn state helpers
- `workflows.py` — 7 predefined workflow templates (GST, Bank, Audit, ITR, Monthly, Document Request, Status)
- `recommendations.py` — proactive work intelligence (priority aggregation)

### `app/llm`
- `base.py` — `LLMProvider` / `LLMMessage` / `ToolSpec` abstraction
- `factory.py` — selects provider from `LLM_PROVIDER`
- `errors.py` — structured, provider-independent LLM exceptions (auth/rate/timeout/invalid/unavailable)
- `key_pool.py` — concurrency-safe OpenRouter multi-key pool with rotation + cooldown
- `context.py` — truncation helpers so large data never reaches the model wholesale
- `providers/` — `mock`, `openai`, `gemini`, `anthropic`, `ollama`, `openrouter`

### `app/tools`
- `registry.py` — formal registry of 23 `ToolDefinition`s
- `*_tools.py` — domain tool groups (client, document, task, meeting, report, reconciliation, workflow, search)

### `app/backend`
- `client.py` — `BackendClient` (httpx): timeouts, safe retries, structured errors
- `auth.py` — backend auth (API key / JWT) handling
- `schemas.py` — backend-facing request/response contracts
- `endpoints.py` — configurable endpoint map via `BACKEND_ENDPOINT_*` env vars

### `app/memory`
- `conversation.py` — short-term per-conversation memory with TTL + cap, pending-action storage
- `context.py` — working memory / context manager

### `app/rag`
- `embeddings.py` — embedding abstraction (mock + sentence-transformers)
- `retriever.py` — retrieval with metadata filtering (client_id, source_type)
- `knowledge.py` — global CA knowledge base (never client-scoped)
- `document_search.py` — client-scoped document retrieval

### `app/safety`
- `permissions.py` — role-permission checks + client isolation
- `validation.py` — input size limits, injection-signal detection, PII redaction, document sanitization
- `pii.py` — PAN/Aadhaar/account number detection & redaction
- `action_policy.py` — risk policy for mutating/destructive actions

### `app/speech`, `app/observability`, `app/schemas`, `app/config`
- `speech/stt.py` — STT abstraction + mock/OpenAI Whisper
- `observability/` — logging, metrics, context vars, request middleware
- `schemas/` — chat, tools, agent contracts
- `fallbacks.py` — graceful degradation (mock providers, degradation manager)

## Key principles

1. **Backend is authoritative.** The engine never opens a database connection;
   all data flows through authenticated HTTP to the Backend.
2. **Provider-independent.** Swapping `LLM_PROVIDER` changes the model without
   changing agent code.
3. **Client isolation.** Per-client retrieval and tool arguments are checked
   against the caller's allowed clients; the Backend enforces the final 403.
4. **Tool allowlisting.** The LLM can only invoke registered tools; every
   argument is validated by a Pydantic model.
5. **Confirmation gating.** Mutating/high-impact tools require explicit user
   confirmation (a pending action stored in conversation memory).
6. **Documents are DATA, never instructions.** Retrieved content is never fed
   verbatim as a system prompt and is screened for injection signals.
7. **Runs offline.** A `MockLLMProvider`, mock embeddings, and the stub
   BackendClient let the whole engine boot and be tested with zero external
   dependencies.
8. **Graceful degradation.** Fallback providers activate automatically on failure.

## Intent routing

`planner.classify_intent` maps a message to one of:

- `general` — CA/accounting knowledge question.
- `client_specific` — question about a specific client.
- `action` — create/update a task, meeting, report, etc.
- `data_analysis` — explain mismatches / reconciliation results.
- `report` — generate a report.
- `unknown`

Classification is tried via the LLM first and falls back to deterministic
heuristics so the engine never depends on network availability.

## Workflow templates

| Workflow | Trigger | Steps | Output |
|----------|---------|-------|--------|
| `gst_reconciliation` | "reconcile gst", "gst mismatch" | summary → exceptions | Reconciliation report table |
| `bank_classification` | "process bank", "bank review" | unreviewed → process | Bank review report |
| `audit_document_check` | "audit document", "audit checklist" | documents → requests | Document checklist |
| `itr_document_check` | "itr document", "tax document" | documents → pending | ITR checklist |
| `monthly_closing` | "monthly review", "client review" | status, pending, deadlines, docs, requests, recon | Monthly review |
| `client_document_request` | "request document", "missing document" | create_request | Request confirmation |
| `client_status_review` | "client status", "what is pending" | status, pending, meetings | Status summary |

## Streaming events

| Event | Description |
|-------|-------------|
| `start` | Turn started |
| `thinking` | Iteration started |
| `tool_started` | Tool invocation began |
| `tool_completed` | Tool finished (ok/error/confirmation) |
| `confirmation_required` | User confirmation needed |
| `token` | Response token delta |
| `workflow_result` | Workflow completed |
| `done` | Turn finished |

## Client data isolation

- RAG retriever enforces `client_id` filter on `client_document` source
- Knowledge base never carries `client_id`
- Tool executor validates `client_id` against user's accessible clients
- Conversation memory isolated per `conversation_id`
- Permissions checked at tool + client level

## Prompt injection defense

- Heuristic detection in `validation.py` (substrings + regex patterns)
- Documents sanitized via `sanitize_document_content()` before LLM context
- Tool results sanitized via `sanitize_tool_result()`
- LLM responses validated via `validate_llm_response()`
- Injection signals logged but not blocked (documents are DATA)

## Graceful degradation

| Service | Fallback |
|---------|----------|
| LLM | `MockLLMProvider` (deterministic responses) |
| STT | `MockSTTProvider` (size-based transcription) |
| Backend | Errors surfaced as safe AI messages |
| RAG | Empty results, clear indication |

Managed by `GracefulDegradation` singleton with status endpoint.

---

## OpenRouter provider

The engine talks to OpenRouter through the same `LLMProvider` interface the
agent already uses. Nothing in `orchestrator.py`, tools, or routes is aware
OpenRouter is in use.

```
Agent
  |  LLMProvider (provider-independent)
  v
OpenRouterProvider
  |  httpx.AsyncClient (reusable, pooled)
  |  OpenRouter /chat/completions (OpenAI-compatible)
  v
Selected model (via model routing)
```

### Key rotation & failure handling

`OpenRouterProvider` owns an `OpenRouterKeyPool` (see `app/llm/key_pool.py`):

- Keys are loaded from `OPENROUTER_API_KEY_1..N` (plus optional single
  `OPENROUTER_API_KEY` fallback), validated, and handed out round-robin under
  an `asyncio.Lock` so concurrent requests never all grab the same key.
- On a retryable failure the failed key is temporarily disabled; another
  healthy key is selected next.
- Cooldown is `OPENROUTER_KEY_COOLDOWN_SECONDS` (default 60s). `401`/`403`
  (invalid key) trigger a much longer hold (≥1h, until reload).
- Retries are bounded by `MAX_LLM_RETRIES` **and** the number of keys —
  whichever is smaller — with exponential backoff, honouring `Retry-After`
  for `429`.
- `400`-class errors are **not** blindly retried (likely a model/schema
  problem) — they raise `LLMInvalidRequestError`.

### Failure classification

| Case | Behaviour |
|------|-----------|
| `401` / `403` | Disable key (long cooldown), try next |
| `429` | Disable key briefly, respect `Retry-After`, try next |
| `5xx` | Temporary provider failure, retry on another key |
| timeout | Retry on another key |
| `400` | Raise `LLMInvalidRequestError` (no blind retry) |
| all keys down | Raise `LLMUnavailableError` (retryable) |

Structured errors (`app/llm/errors.py`) are provider-independent; raw
OpenRouter payloads are never shown to users.

### Model routing

`OPENROUTER_MODEL` is the default. Optional slots `OPENROUTER_FAST_MODEL` and
`OPENROUTER_REASONING_MODEL` let the agent request a capability
(`fast` / `reasoning` / default). The frontend never selects arbitrary models;
unconfigured slots fall back to the default model.

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_PROVIDER` | `mock` | set to `openrouter` to use OpenRouter |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | base URL |
| `OPENROUTER_MODEL` | — | default model |
| `OPENROUTER_FAST_MODEL` | — | fast slot (optional) |
| `OPENROUTER_REASONING_MODEL` | — | reasoning slot (optional) |
| `OPENROUTER_HTTP_REFERER` | — | attribution header (optional) |
| `OPENROUTER_APP_NAME` | `AOS` | `X-Title` attribution header |
| `OPENROUTER_API_KEY_1..5` | — | key pool (only as many as you set) |
| `MAX_LLM_RETRIES` | `3` | max attempts per request |
| `OPENROUTER_KEY_COOLDOWN_SECONDS` | `60` | temporary key cooldown |

### Security

API keys are **never** logged, returned, stored, or committed. Logs reference
keys only by masked form (`****<suffix>`) and integer index. `/health` and
`/ready` return only safe aggregates (configured/healthy key counts, model);
raw `Authorization`/keys never appear. The frontend receives no keys — the
browser talks only to the AI Engine.

### Context control

Large tool results and document extracts are truncated in `app/llm/context.py`
before reaching the model, so big client datasets are not forwarded wholesale.
The backend/ML layer performs heavy data processing; the LLM receives bounded,
structured summaries and relevant exceptions.