"""The agent orchestrator — multi-step reasoning agent with tool chaining.

Flow:
1. Build context (conversation, client, services, working memory)
2. Classify intent / understand task
3. LLM-driven tool planning (not hardcoded)
4. Execute tools with safety gates (permission, confirmation, validation)
5. Iterate: LLM reasons about results → plans next tools → executes
6. Synthesize final answer with citations
7. Persist to memory
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agent.executor import ToolExecutionPlan
from app.agent.planner import classify_intent
from app.agent.prompts import get_system_message
from app.agent.workflows import WorkflowName, get_workflow
from app.agent.recommendations import WorkIntelligence, generate_priorities_response
from app.backend.client import BackendClient
from app.llm.base import LLMMessage, LLMProvider, ToolSpec
from app.llm.context import truncate_tool_result
from app.memory.context import ContextManager
from app.memory.conversation import ConversationMemory, get_conversation_memory
from app.rag.knowledge import get_knowledge_base
from app.rag.document_search import get_document_store
from app.safety.validation import validate_request_size
from app.schemas.agent import ClientContext, IntentType, UserContext
from app.schemas.chat import Source, ToolCallResult
from app.tools.registry import get_registry
from app.observability import metrics
from app.observability.logging import get_logger

logger = get_logger("orchestrator")

MAX_TOOL_ITERATIONS = 5
MAX_TOOLS_PER_TURN = 20


@dataclass
class ToolStep:
    name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    status: str = "pending"


@dataclass
class AgentTurnState:
    conversation_id: str
    user_id: Optional[str]
    user_role: Optional[str]
    client_id: Optional[str]
    client_context: Optional[ClientContext] = None
    message: str = ""
    intent: IntentType = IntentType.UNKNOWN
    tools_executed: List[ToolStep] = field(default_factory=list)
    sources: List[Source] = field(default_factory=list)
    iterations: int = 0
    final_answer: str = ""
    requires_confirmation: bool = False
    pending_tool: Optional[str] = None
    pending_args: Optional[Dict[str, Any]] = None


class AgentOrchestrator:
    def __init__(
        self,
        llm: LLMProvider,
        backend: BackendClient,
        memory: ConversationMemory | None = None,
    ):
        self.llm = llm
        self.backend = backend
        self.memory = memory or get_conversation_memory()
        self.registry = get_registry()
        self._context = ContextManager()

    async def run(
        self,
        *,
        message: str,
        client_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        from app.schemas.chat import ChatResponse

        conv = self.memory.get_or_create(conversation_id, user_id)
        conversation_id = conv.conversation_id

        validate_request_size(message)

        user = UserContext(user_id=user_id, user_role=user_role)
        client = ClientContext(client_id=client_id) if client_id else None

        state = AgentTurnState(
            conversation_id=conversation_id,
            user_id=user_id,
            user_role=user_role,
            client_id=client_id,
            client_context=client,
            message=message,
        )

        start = time.time()

        try:
            state.intent, workflow = await classify_intent(message, self.llm, client_id=client_id)
            state.client_context = await self._enrich_client_context(client, user)
            
            exec_plan = ToolExecutionPlan(
                backend=self.backend,
                user=user,
                client=state.client_context or ClientContext(),
                context=ContextManager(),
                llm=self.llm,
                conversation_id=conversation_id,
            )
            self.executor = exec_plan
            
            # Handle proactive recommendations ("what should I do")
            from app.agent.planner import _PRIORITY_HINTS
            if any(hint in message.lower() for hint in _PRIORITY_HINTS) and state.client_id:
                work_intel = WorkIntelligence(self.backend)
                state.final_answer = await generate_priorities_response(
                    work_intel, user, state.client_id, state.client_context
                )
                # Skip normal agent loop
            # If workflow detected, execute it
            elif workflow:
                workflow_result = await self._execute_workflow(workflow, state, exec_plan)
                if workflow_result is not None:
                    state.final_answer = workflow_result
                elif state.requires_confirmation:
                    return  # Waiting for confirmation
                else:
                    # Workflow execution failed - fall back to agent loop
                    await self._run_agent_loop(state, exec_plan)
            else:
                await self._run_agent_loop(state, exec_plan)

            # Final synthesis (if not already set by workflow)
            if not state.final_answer:
                state.final_answer = await self._synthesize_answer(state)

            # RAG for general knowledge
            if state.intent == IntentType.GENERAL and not state.tools_executed:
                for hit in get_knowledge_base().query(message, top_k=3):
                    state.sources.append(
                        Source(source_type="knowledge", title=hit.metadata.get("title", ""))
                    )

        except Exception as e:
            logger.error("orchestrator error", extra={"error": str(e), "request_id": request_id})
            state.final_answer = f"I encountered an error: {str(e)}"

        # Persist conversation
        self.memory.add_turn(conversation_id, {"role": "user", "content": message})
        self.memory.add_turn(conversation_id, {"role": "assistant", "content": state.final_answer})

        latency_ms = (time.time() - start) * 1000
        try:
            metrics.record_turn(
                success=bool(state.final_answer and not state.final_answer.startswith("I encountered")),
                latency_ms=latency_ms,
                model=getattr(self.llm, "name", "unknown"),
                tool_calls=len(state.tools_executed),
            )
        except Exception:
            pass

        pending = self.memory.get_pending_action(conversation_id)
        return ChatResponse(
            conversation_id=conversation_id,
            user_id=user_id,
            message=state.final_answer,
            tool_calls=[
                ToolCallResult(
                    name=s.name,
                    arguments=s.arguments,
                    status=s.status,
                    result=s.result,
                    error=s.error,
                )
                for s in state.tools_executed
            ],
            requires_confirmation=pending is not None,
            pending_confirmation=pending.get("tool") if pending else None,
            pending_confirmation_args=pending.get("args") if pending else {},
            sources=state.sources,
            request_id=request_id or "",
        )

    async def run_stream(
        self,
        *,
        message: str,
        client_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        """Streaming version of run - yields SSE events for each step."""
        import json
        from app.schemas.chat import ChatResponse
        
        conv = self.memory.get_or_create(conversation_id, user_id)
        conversation_id = conv.conversation_id
        validate_request_size(message)

        user = UserContext(user_id=user_id, user_role=user_role)
        client = ClientContext(client_id=client_id) if client_id else None

        state = AgentTurnState(
            conversation_id=conversation_id,
            user_id=user_id,
            user_role=user_role,
            client_id=client_id,
            client_context=client,
            message=message,
        )

        start = time.time()

        try:
            state.intent, workflow = await classify_intent(message, self.llm, client_id=client_id)
            state.client_context = await self._enrich_client_context(client, user)
            
            exec_plan = ToolExecutionPlan(
                backend=self.backend,
                user=user,
                client=state.client_context or ClientContext(),
                context=ContextManager(),
                llm=self.llm,
                conversation_id=conversation_id,
            )
            self.executor = exec_plan
            
            # If workflow detected, execute it with streaming
            if workflow:
                workflow_result = await self._execute_workflow_stream(workflow, state, exec_plan)
                if workflow_result:
                    state.final_answer = workflow_result
                else:
                    # Waiting for confirmation
                    pass
            else:
                # Run agent loop with streaming
                async for event in self._run_agent_loop_stream(state, exec_plan):
                    yield event

            # Final synthesis if needed
            if not state.final_answer:
                state.final_answer = await self._synthesize_answer(state)

            # RAG for general knowledge
            if state.intent == IntentType.GENERAL and not state.tools_executed:
                for hit in get_knowledge_base().query(message, top_k=3):
                    state.sources.append(
                        Source(source_type="knowledge", title=hit.metadata.get("title", ""))
                    )

        except Exception as e:
            logger.error("orchestrator stream error", extra={"error": str(e), "request_id": request_id})
            state.final_answer = f"I encountered an error: {str(e)}"

        # Persist conversation
        self.memory.add_turn(conversation_id, {"role": "user", "content": message})
        self.memory.add_turn(conversation_id, {"role": "assistant", "content": state.final_answer})

        latency_ms = (time.time() - start) * 1000
        try:
            metrics.record_turn(
                success=bool(state.final_answer and not state.final_answer.startswith("I encountered")),
                latency_ms=latency_ms,
                model=getattr(self.llm, "name", "unknown"),
                tool_calls=len(state.tools_executed),
            )
        except Exception:
            pass

        # Stream final answer token by token
        text = state.final_answer
        for i in range(0, len(text), 16):
            yield {"event": "token", "data": json.dumps({"content": text[i : i + 16]})}

        pending = self.memory.get_pending_action(conversation_id)
        response = ChatResponse(
            conversation_id=conversation_id,
            user_id=user_id,
            message=state.final_answer,
            tool_calls=[
                ToolCallResult(
                    name=s.name,
                    arguments=s.arguments,
                    status=s.status,
                    result=s.result,
                    error=s.error,
                )
                for s in state.tools_executed
            ],
            requires_confirmation=pending is not None,
            pending_confirmation=pending.get("tool") if pending else None,
            pending_confirmation_args=pending.get("args") if pending else {},
            sources=state.sources,
            request_id=request_id or "",
        )

        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "conversation_id": response.conversation_id,
                    "requires_confirmation": response.requires_confirmation,
                    "tool_calls": [
                        {"name": s.name, "arguments": s.arguments, "status": s.status}
                        for s in state.tools_executed
                    ],
                }
            ),
        }

    async def _run_agent_loop_stream(self, state: AgentTurnState, exec_plan: ToolExecutionPlan):
        """Multi-step agent loop with streaming events."""
        conversation_history = self.memory.get(state.conversation_id)
        history_messages = conversation_history.to_prompt_messages() if conversation_history else []

        import json
        
        system_msg = get_system_message(
            user_role=state.user_role,
            client_name=state.client_context.client_name if state.client_context else None,
            available_tools=[t.name for t in self.registry.all()],
        )

        messages = [system_msg] + [
            LLMMessage(m["role"], m["content"]) for m in history_messages
        ] + [LLMMessage("user", state.message)]

        tools_spec = [t.to_llm_spec() for t in self.registry.all()]

        while state.iterations < MAX_TOOL_ITERATIONS:
            state.iterations += 1
            yield {"event": "thinking", "data": json.dumps({"iteration": state.iterations})}

            result = await self.llm.generate(
                messages=messages,
                tools=tools_spec,
                temperature=0.1,
            )

            if result.tool_calls:
                for tc in result.tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc.get("arguments", {})

                    if len(state.tools_executed) >= MAX_TOOLS_PER_TURN:
                        logger.warning("Max tools per turn reached")
                        break

                    # Tool started event
                    yield {"event": "tool_started", "data": json.dumps({
                        "tool": tool_name,
                        "arguments": tool_args,
                    })}

                    tool_step = ToolStep(name=tool_name, arguments=tool_args)
                    state.tools_executed.append(tool_step)

                    exec_result = await exec_plan.execute(
                        tool_name,
                        tool_args,
                        explicit_intent=state.intent == IntentType.ACTION,
                    )

                    tool_step.status = exec_result.status.value
                    tool_step.result = exec_result.data
                    tool_step.error = exec_result.error

                    # Tool completed event
                    yield {"event": "tool_completed", "data": json.dumps({
                        "tool": tool_name,
                        "status": exec_result.status.value,
                        "result": str(exec_result.data)[:500] if exec_result.data else None,
                        "error": exec_result.error,
                    })}

                    messages.append(
                        LLMMessage("tool", f"Tool {tool_name} returned: {truncate_tool_result(exec_result.data or exec_result.error)}")
                    )

                    if exec_result.status.value in ("needs_confirmation", "blocked", "error"):
                        state.requires_confirmation = exec_result.status.value == "needs_confirmation"
                        state.pending_tool = tool_name
                        state.pending_args = tool_args
                        yield {"event": "confirmation_required", "data": json.dumps({
                            "tool": tool_name,
                            "arguments": tool_args,
                        })}
                        return

                continue

            if result.content:
                state.final_answer = result.content
            break

        if not state.final_answer:
            state.final_answer = await self._synthesize_answer(state)

    async def _execute_workflow_stream(
        self,
        workflow_name: WorkflowName,
        state: AgentTurnState,
        exec_plan: ToolExecutionPlan,
    ):
        """Execute a predefined workflow template with streaming."""
        import json
        workflow = get_workflow(workflow_name)
        if not workflow:
            return

        missing = [inp for inp in workflow.required_inputs if not getattr(state, inp, None)]
        if missing and "client_id" in missing and not state.client_id:
            yield {"event": "error", "data": json.dumps({
                "message": "This workflow requires a client_id. Please specify which client."
            })}
            return

        step_results = {}
        for step in workflow.steps:
            args = {}
            for k, v in step.args_template.items():
                if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
                    key = v[1:-1]
                    args[k] = getattr(state, key, None) or step_results.get(key)
                else:
                    args[k] = v

            yield {"event": "tool_started", "data": json.dumps({
                "tool": step.tool,
                "arguments": args,
                "workflow_step": step.name,
            })}

            tool_step = ToolStep(name=step.name, arguments=args)
            state.tools_executed.append(tool_step)

            exec_result = await exec_plan.execute(
                step.tool,
                args,
                explicit_intent=state.intent == IntentType.ACTION,
            )

            tool_step.status = exec_result.status.value
            tool_step.result = exec_result.data
            tool_step.error = exec_result.error

            yield {"event": "tool_completed", "data": json.dumps({
                "tool": step.tool,
                "status": exec_result.status.value,
                "result": str(exec_result.data)[:500] if exec_result.data else None,
                "error": exec_result.error,
            })}

            if exec_result.status.value == "ok":
                step_results[step.output_key or step.name] = exec_result.data
            elif exec_result.status.value in ("needs_confirmation", "blocked", "error"):
                state.requires_confirmation = exec_result.status.value == "needs_confirmation"
                state.pending_tool = step.tool
                state.pending_args = args
                yield {"event": "confirmation_required", "data": json.dumps({
                    "tool": step.tool,
                    "arguments": args,
                })}
                return

        result = await self._format_workflow_output(workflow, step_results, state)
        yield {"event": "workflow_result", "data": json.dumps({"result": result})}

    async def _enrich_client_context(
        self, client: Optional[ClientContext], user: UserContext
    ) -> Optional[ClientContext]:
        """Fetch full client context from backend including selected services."""
        if not client or not client.client_id:
            return client

        try:
            # Get client details
            client_data = await self.backend.get(
                f"/api/v1/ai-tools/get_client",
                params={"client_id": client.client_id},
                user_id=user.user_id,
                user_role=user.user_role,
            )
            if client_data:
                enriched = ClientContext(
                    client_id=client.client_id,
                    client_name=client_data.get("name"),
                    organization_name=client_data.get("organization_name"),
                    financial_year=client_data.get("financial_year"),
                    selected_services=client_data.get("selected_services", []),
                    industry=client_data.get("industry"),
                    current_period=client_data.get("current_period"),
                    user_id=user.user_id,
                    user_role=user.user_role,
                )
                return enriched
        except Exception as e:
            logger.warning("Failed to enrich client context", extra={"error": str(e)})
        return client

    async def _run_agent_loop(self, state: AgentTurnState, exec_plan: ToolExecutionPlan) -> None:
        """Multi-step agent loop: LLM plans tools, executes, reasons, repeats."""
        conversation_history = self.memory.get(state.conversation_id)
        history_messages = conversation_history.to_prompt_messages() if conversation_history else []

        # Build initial messages for LLM
        system_msg = get_system_message(
            user_role=state.user_role,
            client_name=state.client_context.client_name if state.client_context else None,
            available_tools=[t.name for t in self.registry.all()],
        )

        messages = [system_msg] + [
            LLMMessage(m["role"], m["content"]) for m in history_messages
        ] + [LLMMessage("user", state.message)]

        tools_spec = [t.to_llm_spec() for t in self.registry.all()]

        while state.iterations < MAX_TOOL_ITERATIONS:
            state.iterations += 1

            # LLM decides next action
            result = await self.llm.generate(
                messages=messages,
                tools=tools_spec,
                temperature=0.1,
            )

            if result.tool_calls:
                # Execute each tool call
                for tc in result.tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc.get("arguments", {})

                    if len(state.tools_executed) >= MAX_TOOLS_PER_TURN:
                        logger.warning("Max tools per turn reached")
                        break

                    # Check if this is a continuation of a previous tool result
                    tool_step = ToolStep(name=tool_name, arguments=tool_args)
                    state.tools_executed.append(tool_step)

                    # Execute with safety
                    exec_result = await exec_plan.execute(
                        tool_name,
                        tool_args,
                        explicit_intent=state.intent == IntentType.ACTION,
                    )

                    tool_step.status = exec_result.status.value
                    tool_step.result = exec_result.data
                    tool_step.error = exec_result.error

                    # Add tool result to conversation for next iteration
                    messages.append(
                        LLMMessage("tool", f"Tool {tool_name} returned: {truncate_tool_result(exec_result.data or exec_result.error)}")
                    )

                    if exec_result.status.value in ("needs_confirmation", "blocked", "error"):
                        state.requires_confirmation = exec_result.status.value == "needs_confirmation"
                        state.pending_tool = tool_name
                        state.pending_args = tool_args
                        return  # Stop and wait for confirmation

                # Continue loop for next reasoning step
                continue

            # No tool calls - LLM provided final answer
            if result.content:
                state.final_answer = result.content
            break

        # If loop ended without explicit answer, synthesize
        if not state.final_answer:
            state.final_answer = await self._synthesize_answer(state)

    async def _synthesize_answer(self, state: AgentTurnState) -> str:
        """Synthesize final answer from tool results and context."""
        if not state.tools_executed:
            return "I couldn't find any relevant information for your request."

        # Collect successful results
        successful = [s for s in state.tools_executed if s.status == "ok" and s.result]
        if not successful:
            errors = [s.error for s in state.tools_executed if s.error]
            return f"I wasn't able to retrieve that information. Errors: {'; '.join(errors) if errors else 'Unknown error'}"

        # Build synthesis prompt
        tool_results_summary = "\n".join(
            f"- {s.name}({s.arguments}): {s.result}" for s in successful
        )

        synthesis_prompt = (
            f"User asked: {state.message}\n\n"
            f"Tool results:\n{tool_results_summary}\n\n"
            f"Client context: {state.client_context.client_name if state.client_context else 'N/A'}\n"
            f"Services: {state.client_context.selected_services if state.client_context else 'N/A'}\n\n"
            "Provide a concise, professional answer. Use tables/bullets where helpful. "
            "Cite tool results. Mark suggestions as suggestions. "
            "If data is missing, say so. Never invent data."
        )

        result = await self.llm.generate(
            messages=[
                LLMMessage("system", "You are AOS Copilot. Synthesize tool results into a clear answer."),
                LLMMessage("user", synthesis_prompt),
            ],
            temperature=0.2,
        )
        return result.content or "I have the data but couldn't format a response."

    async def _execute_workflow(
        self,
        workflow_name: WorkflowName,
        state: AgentTurnState,
        exec_plan: ToolExecutionPlan,
    ) -> Optional[str]:
        """Execute a predefined workflow template."""
        workflow = get_workflow(workflow_name)
        if not workflow:
            return None

        # Check required inputs
        missing = [inp for inp in workflow.required_inputs if not getattr(state, inp, None)]
        if missing and "client_id" in missing and not state.client_id:
            return f"This workflow requires a client_id. Please specify which client."

        # Execute workflow steps
        step_results = {}
        for step in workflow.steps:
            # Build args from template
            args = {}
            for k, v in step.args_template.items():
                if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
                    key = v[1:-1]
                    args[k] = getattr(state, key, None) or step_results.get(key)
                else:
                    args[k] = v

            # Execute tool
            tool_step = ToolStep(name=step.name, arguments=args)
            state.tools_executed.append(tool_step)

            exec_result = await exec_plan.execute(
                step.tool,
                args,
                explicit_intent=state.intent == IntentType.ACTION,
            )

            tool_step.status = exec_result.status.value
            tool_step.result = exec_result.data
            tool_step.error = exec_result.error

            if exec_result.status.value == "ok":
                step_results[step.output_key or step.name] = exec_result.data
            elif exec_result.status.value in ("needs_confirmation", "blocked", "error"):
                state.requires_confirmation = exec_result.status.value == "needs_confirmation"
                state.pending_tool = step.tool
                state.pending_args = args
                return None  # Stop for confirmation

        # Format output based on workflow
        return await self._format_workflow_output(workflow, step_results, state)

    async def _format_workflow_output(
        self,
        workflow,
        step_results: Dict[str, Any],
        state: AgentTurnState,
    ) -> str:
        """Format workflow results into a structured response."""
        client_name = state.client_context.client_name if state.client_context else state.client_id

        if workflow.name == WorkflowName.GST_RECONCILIATION:
            return self._format_reconciliation_report(client_name, step_results)
        elif workflow.name == WorkflowName.BANK_CLASSIFICATION:
            return self._format_bank_report(client_name, step_results)
        elif workflow.name == WorkflowName.MONTHLY_CLOSING:
            return self._format_monthly_review(client_name, step_results)
        elif workflow.name == WorkflowName.CLIENT_STATUS_REVIEW:
            return self._format_status_summary(client_name, step_results)
        elif workflow.name == WorkflowName.CLIENT_DOCUMENT_REQUEST:
            return self._format_request_confirmation(client_name, step_results)
        elif workflow.name in (WorkflowName.AUDIT_DOCUMENT_CHECK, WorkflowName.ITR_DOCUMENT_CHECK):
            return self._format_document_checklist(client_name, step_results, workflow.name.value)

        # Generic fallback
        return await self._synthesize_answer(state)

    def _format_reconciliation_report(self, client_name: str, results: Dict[str, Any]) -> str:
        summary = results.get("summary", {})
        exceptions = results.get("exceptions", [])

        lines = [f"**GST Reconciliation — {client_name}**\n"]
        
        if summary:
            lines.append(
                f"| Metric | Count |\n|---|---|\n"
                f"| Matched | {summary.get('matched', 0)} |\n"
                f"| Missing from Portal | {summary.get('mismatches', 0)} |\n"
                f"| Total Transactions | {summary.get('total_transactions', 0)} |\n"
                f"| Period | {summary.get('period', 'N/A')} |"
            )
        
        if exceptions:
            lines.append(f"\n**Top Mismatches ({len(exceptions)} total):**")
            for exc in exceptions[:10]:
                amt = exc.get('amount', 'N/A')
                desc = exc.get('description', 'No description')
                lines.append(f"- {desc} — ₹{amt}")
            if len(exceptions) > 10:
                lines.append(f"... and {len(exceptions) - 10} more")

        lines.append("\n*Professional review may be required for client-specific filing/advice.*")
        return "\n".join(lines)

    def _format_bank_report(self, client_name: str, results: Dict[str, Any]) -> str:
        unreviewed = results.get("unreviewed", [])
        processing = results.get("processing_result", {})

        lines = [f"**Bank Statement Review — {client_name}**\n"]
        
        if processing:
            lines.append(f"Processing: {processing}")
        
        if unreviewed:
            total = len(unreviewed)
            lines.append(f"Transactions needing review: **{total}**")
            # Show top 5 by amount
            sorted_tx = sorted(unreviewed, key=lambda x: x.get('amount', 0) or 0, reverse=True)
            for tx in sorted_tx[:5]:
                amt = tx.get('amount', 'N/A')
                desc = tx.get('description', 'No description')
                lines.append(f"- ₹{amt}: {desc}")
            if total > 5:
                lines.append(f"... and {total - 5} more")
        else:
            lines.append("All transactions reviewed ✓")

        lines.append("\n*Review uncertain entries before finalizing classifications.*")
        return "\n".join(lines)

    def _format_monthly_review(self, client_name: str, results: Dict[str, Any]) -> str:
        lines = [f"**Monthly Client Review — {client_name}**\n"]
        
        status = results.get("status", {})
        if status:
            lines.append(f"**Status:** {status.get('summary', status.get('status', 'Active'))}")

        pending = results.get("pending", [])
        if pending:
            lines.append(f"\n**Pending Work ({len(pending)}):**")
            for p in pending[:5]:
                lines.append(f"- {p.get('title', 'Task')} (Due: {p.get('due', 'N/A')})")

        deadlines = results.get("deadlines", [])
        if deadlines:
            lines.append(f"\n**Upcoming Deadlines ({len(deadlines)}):**")
            for d in deadlines[:5]:
                lines.append(f"- {d.get('title', 'Deadline')}: {d.get('due_date', 'N/A')}")

        recon = results.get("reconciliation", {})
        if recon:
            lines.append(f"\n**GST Reconciliation:** {recon.get('overall_status', 'N/A')} "
                        f"({recon.get('mismatches', 0)} mismatches)")

        requests = results.get("requests", [])
        if requests:
            lines.append(f"\n**Open Client Requests ({len(requests)}):**")
            for r in requests[:3]:
                lines.append(f"- {r.get('subject', 'Request')}")

        return "\n".join(lines)

    def _format_status_summary(self, client_name: str, results: Dict[str, Any]) -> str:
        lines = [f"**Client Status — {client_name}**\n"]
        
        status = results.get("status", {})
        if status:
            lines.append(f"**Current Status:** {status.get('summary', status.get('status', 'Active'))}")
            if status.get('current_period'):
                lines.append(f"**Period:** {status['current_period']}")

        pending = results.get("pending", [])
        if pending:
            lines.append(f"\n**Pending Items ({len(pending)}):**")
            for p in pending[:5]:
                lines.append(f"- {p.get('title', 'Item')} — Due: {p.get('due', 'N/A')}")

        meetings = results.get("meetings", [])
        if meetings:
            lines.append(f"\n**Upcoming Meetings ({len(meetings)}):**")
            for m in meetings[:3]:
                lines.append(f"- {m.get('title', 'Meeting')}: {m.get('scheduled_at', 'TBD')}")

        return "\n".join(lines)

    def _format_request_confirmation(self, client_name: str, results: Dict[str, Any]) -> str:
        request = results.get("request", {})
        if request:
            return (
                f"✅ **Client Request Created**\n\n"
                f"**Client:** {client_name}\n"
                f"**Subject:** {request.get('subject', 'N/A')}\n"
                f"**Status:** {request.get('status', 'open')}\n"
                f"**Request ID:** {request.get('id', 'N/A')}"
            )
        return "Request created but no confirmation received from backend."

    def _format_document_checklist(self, client_name: str, results: Dict[str, Any], check_type: str) -> str:
        docs = results.get("documents", [])
        requests = results.get("requests", [])
        
        lines = [f"**{check_type.replace('_', ' ').title()} — {client_name}**\n"]
        
        if docs:
            lines.append(f"**Documents Found ({len(docs)}):**")
            for d in docs:
                lines.append(f"- {d.get('title', 'Document')} ({d.get('doc_type', 'N/A')})")
        else:
            lines.append("**No documents found.**")
        
        if requests:
            lines.append(f"\n**Open Requests ({len(requests)}):**")
            for r in requests:
                lines.append(f"- {r.get('subject', 'Request')}")
        
        return "\n".join(lines)

    def get_executor(self) -> "ToolExecutionPlan | None":
        if self.executor is None:
            self.executor = ToolExecutionPlan(
                backend=self.backend,
                user=UserContext(),
                client=ClientContext(),
                context=ContextManager(),
                llm=self.llm,
            )
        return self.executor


# Backward compatibility
def _plan_tools(intent: IntentType) -> List[str]:
    mapping = {
        IntentType.GENERAL: ["list_clients"],
        IntentType.CLIENT_SPECIFIC: ["get_client_status", "get_pending_work"],
        IntentType.DATA_ANALYSIS: ["get_reconciliation_summary"],
        IntentType.REPORT: ["get_client_status", "get_pending_work"],
        IntentType.ACTION: [],
        IntentType.UNKNOWN: [],
    }
    return mapping.get(intent, [])