"""System prompt builder.

Loads prompts/system.txt for the base system prompt and optionally appends
CA-specific instructions from prompts/ca_copilot.txt.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from app.llm.base import LLMMessage

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_system_prompt() -> str:
    path = _PROMPTS_DIR / "system.txt"
    if path.exists():
        return path.read_text()
    return _DEFAULT_SYSTEM


def load_ca_copilot_prompt() -> str:
    path = _PROMPTS_DIR / "ca_copilot.txt"
    if path.exists():
        return path.read_text()
    return _DEFAULT_COPILOT


def get_system_message(
    *,
    user_role: Optional[str] = None,
    client_name: Optional[str] = None,
    available_tools: Optional[List[str]] = None,
) -> LLMMessage:
    text = load_system_prompt()

    # CA-specific context injection (respecting role / client) from ca_copilot.txt
    copilot = load_ca_copilot_prompt()

    full = f"{text}\n\n---\n\n{copilot}"
    if user_role:
        full += f"\n\nCURRENT USER ROLE: {user_role}"
    if client_name:
        full += f"\n\nCURRENT CLIENT: {client_name}"
    if available_tools:
        full += f"\n\nAVAILABLE TOOLS: {', '.join(available_tools)}"

    return LLMMessage("system", full)


_DEFAULT_SYSTEM = """You are the AOS AI Copilot — a professional Accounting Operating System assistant for Chartered Accountants.

CORE PRINCIPLES:
- Be precise and professional. Distinguish between known facts and assumptions.
- NEVER fabricate client data, compliance status, or filing status.
- NEVER claim a government filing or Tally import occurred unless the backend confirms it.
- NEVER call an anomaly "fraud" — call it a "mismatch" / "exception" instead.
- Clearly mark AI suggestions vs confirmed facts.
- Ask for clarification when required info is missing.
- Cite retrieved client documents/data where possible.
- Respect permissions. Protect sensitive financial information.
"""

_DEFAULT_COPILOT = """CA COPILOT ADDITIONAL GUIDANCE:
- When analysing a client's GST reconciliation, explain mismatches in plain language.
- For Tally export, always confirm the client and period before proceeding.
- For deadlines, clearly state which are confirmed by the backend.
- Final professional review is always required for tax/compliance advice.
"""
