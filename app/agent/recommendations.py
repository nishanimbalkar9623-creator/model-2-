"""Proactive Work Intelligence — recommendations based on backend data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.agent.workflows import WorkflowName
from app.schemas.agent import ClientContext, UserContext


@dataclass
class PriorityItem:
    """A prioritized work item."""
    title: str
    description: str
    priority: str  # "high" | "medium" | "low"
    category: str  # "gst" | "audit" | "bank" | "deadline" | "meeting" | "task" | "document"
    client_id: str
    client_name: str
    due_date: Optional[str] = None
    amount: Optional[float] = None
    action: Optional[str] = None
    tool: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None


class WorkIntelligence:
    """Generates proactive recommendations from backend data."""
    
    def __init__(self, backend):
        self.backend = backend
    
    async def get_priorities(
        self,
        user: UserContext,
        client_id: Optional[str] = None,
        client_context: Optional[ClientContext] = None,
    ) -> List[PriorityItem]:
        """Aggregate and rank priority items across all domains."""
        items = []
        
        # Determine client scope
        client_ids = [client_id] if client_id else []
        if not client_ids and client_context:
            client_ids = [client_context.client_id] if client_context.client_id else []
        
        # If no specific client, we'd need to fetch all accessible clients
        # For now, focus on single client
        if not client_ids:
            return []
        
        cid = client_ids[0]
        cname = client_context.client_name if client_context else cid
        
        # Fetch data in parallel-ish manner
        items.extend(await self._get_gst_priorities(cid, cname))
        items.extend(await self._get_bank_priorities(cid, cname))
        items.extend(await self._get_deadline_priorities(cid, cname))
        items.extend(await self._get_task_priorities(cid, cname))
        items.extend(await self._get_meeting_priorities(cid, cname))
        items.extend(await self._get_document_priorities(cid, cname))
        items.extend(await self._get_request_priorities(cid, cname))
        
        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        items.sort(key=lambda x: (priority_order.get(x.priority, 3), x.due_date or ""))
        
        return items
    
    async def _get_gst_priorities(self, client_id: str, client_name: str) -> List[PriorityItem]:
        items = []
        try:
            summary = await self.backend.get(
                "/api/v1/ai-tools/get_reconciliation_summary",
                params={"client_id": client_id},
            )
            if summary and summary.get("mismatches", 0) > 0:
                priority = "high" if summary["mismatches"] > 20 else "medium"
                items.append(PriorityItem(
                    title=f"GST Reconciliation — {summary['mismatches']} mismatches",
                    description=f"Period: {summary.get('period', 'N/A')}. "
                               f"Matched: {summary.get('matched', 0)}, "
                               f"Total: {summary.get('total_transactions', 0)}",
                    priority=priority,
                    category="gst",
                    client_id=client_id,
                    client_name=client_name,
                    action="Review mismatches",
                    tool="get_reconciliation_exceptions",
                    tool_args={"client_id": client_id, "status": "open"},
                ))
        except Exception:
            pass
        return items
    
    async def _get_bank_priorities(self, client_id: str, client_name: str) -> List[PriorityItem]:
        items = []
        try:
            unreviewed = await self.backend.get(
                "/api/v1/ai-tools/get_unreviewed_bank_transactions",
                params={"client_id": client_id, "limit": 50},
            )
            if unreviewed:
                total = len(unreviewed)
                priority = "high" if total > 50 else "medium"
                max_amt = max((t.get("amount", 0) or 0) for t in unreviewed)
                items.append(PriorityItem(
                    title=f"Bank Statement Review — {total} pending",
                    description=f"Largest unreviewed: ₹{max_amt:,.0f}",
                    priority=priority,
                    category="bank",
                    client_id=client_id,
                    client_name=client_name,
                    amount=max_amt,
                    action="Review transactions",
                    tool="get_unreviewed_bank_transactions",
                    tool_args={"client_id": client_id, "limit": 20},
                ))
        except Exception:
            pass
        return items
    
    async def _get_deadline_priorities(self, client_id: str, client_name: str) -> List[PriorityItem]:
        items = []
        try:
            deadlines = await self.backend.get(
                "/api/v1/ai-tools/get_upcoming_deadlines",
                params={"client_id": client_id, "days_ahead": 30},
            )
            if deadlines:
                for dl in deadlines[:3]:
                    items.append(PriorityItem(
                        title=f"Deadline: {dl.get('title', 'Compliance')}",
                        description=f"Due: {dl.get('due_date', 'N/A')} — {dl.get('category', '')}",
                        priority="high",
                        category="deadline",
                        client_id=client_id,
                        client_name=client_name,
                        due_date=dl.get("due_date"),
                        action="Prepare filing",
                    ))
        except Exception:
            pass
        return items
    
    async def _get_task_priorities(self, client_id: str, client_name: str) -> List[PriorityItem]:
        items = []
        try:
            pending = await self.backend.get(
                "/api/v1/ai-tools/get_pending_work",
                params={"client_id": client_id},
            )
            if pending:
                overdue = [p for p in pending if p.get("due") and p.get("status") != "done"]
                high_priority = [p for p in pending if p.get("priority") == "high"]
                
                for task in (overdue + high_priority)[:5]:
                    items.append(PriorityItem(
                        title=f"Task: {task.get('title', 'Work item')}",
                        description=f"Due: {task.get('due', 'N/A')} — Status: {task.get('status', 'pending')}",
                        priority="high" if task in overdue else "medium",
                        category="task",
                        client_id=client_id,
                        client_name=client_name,
                        due_date=task.get("due"),
                        action="Complete task",
                        tool="update_task",
                        tool_args={"task_id": task.get("id"), "status": "in_progress"},
                    ))
        except Exception:
            pass
        return items
    
    async def _get_meeting_priorities(self, client_id: str, client_name: str) -> List[PriorityItem]:
        items = []
        try:
            meetings = await self.backend.get(
                "/api/v1/ai-tools/get_client_meetings",
                params={"client_id": client_id, "status": "scheduled"},
            )
            if meetings:
                for mtg in meetings[:3]:
                    items.append(PriorityItem(
                        title=f"Meeting: {mtg.get('title', 'Client meeting')}",
                        description=f"Scheduled: {mtg.get('scheduled_at', 'TBD')}",
                        priority="medium",
                        category="meeting",
                        client_id=client_id,
                        client_name=client_name,
                        due_date=mtg.get("scheduled_at"),
                        action="Prepare for meeting",
                    ))
        except Exception:
            pass
        return items
    
    async def _get_document_priorities(self, client_id: str, client_name: str) -> List[PriorityItem]:
        items = []
        try:
            docs = await self.backend.get(
                "/api/v1/ai-tools/get_client_documents",
                params={"client_id": client_id, "limit": 100},
            )
            # Check for missing document types based on services
            if docs is not None:
                doc_types = {d.get("doc_type") for d in docs if d.get("doc_type")}
                # This would be enhanced with service-aware expected documents
                pass
        except Exception:
            pass
        return items
    
    async def _get_request_priorities(self, client_id: str, client_name: str) -> List[PriorityItem]:
        items = []
        try:
            requests = await self.backend.get(
                "/api/v1/ai-tools/get_client_requests",
                params={"client_id": client_id, "status": "open"},
            )
            if requests:
                for req in requests[:3]:
                    items.append(PriorityItem(
                        title=f"Client Request: {req.get('subject', 'Document request')}",
                        description=f"Status: {req.get('status', 'open')} — Created: {req.get('created_at', 'N/A')}",
                        priority="medium",
                        category="document",
                        client_id=client_id,
                        client_name=client_name,
                        action="Follow up with client",
                    ))
        except Exception:
            pass
        return items


async def generate_priorities_response(
    work_intel: WorkIntelligence,
    user: UserContext,
    client_id: Optional[str] = None,
    client_context: Optional[ClientContext] = None,
) -> str:
    """Generate a formatted priorities response."""
    items = await work_intel.get_priorities(user, client_id, client_context)
    
    if not items:
        return "No priority items found. You're all caught up! 🎉"
    
    lines = ["**Top Priorities:**\n"]
    
    for i, item in enumerate(items[:10], 1):
        emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(item.priority, "⚪")
        lines.append(f"{i}. {emoji} **{item.title}** ({item.category})")
        lines.append(f"   {item.description}")
        if item.due_date:
            lines.append(f"   📅 Due: {item.due_date}")
        if item.action:
            lines.append(f"   → *Suggested: {item.action}*")
        lines.append("")
    
    if len(items) > 10:
        lines.append(f"... and {len(items) - 10} more items.")
    
    return "\n".join(lines)