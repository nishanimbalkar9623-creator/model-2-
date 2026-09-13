"""Tests for the tool registry and Pydantic argument validation."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path for direct execution
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.tools.registry import get_registry


def test_registry_populated():
    reg = get_registry()
    names = {t.name for t in reg.all()}
    assert "list_clients" in names
    assert "create_task" in names
    assert "run_gst_reconciliation" in names
    assert len(names) >= 15


def test_tool_descriptor_fields():
    reg = get_registry()
    create_task = reg.get("create_task")
    assert create_task is not None
    d = create_task.descriptor
    assert d.name == "create_task"
    assert d.kind.value == "action"
    assert "title" in d.parameters_schema["properties"]


def test_create_task_validation():
    from app.tools.registry import get_registry
    from app.safety.validation import ToolArgValidationError, validate_tool_args

    tool = get_registry().get("create_task")
    valid = validate_tool_args(tool.input_model, {"title": "Do ITR", "priority": "high"})
    assert valid.title == "Do ITR"

    try:
        validate_tool_args(tool.input_model, {"priority": "superhigh"})
        raised = False
    except ToolArgValidationError:
        raised = True
    assert raised


def test_generate_tally_export_requires_confirmation():
    reg = get_registry()
    tool = reg.get("generate_tally_export")
    assert tool.requires_confirmation is True
    assert tool.destructive is False


def test_run_reconciliation_confirmation_flag():
    from app.safety.action_policy import requires_confirmation
    from app.tools.registry import get_registry

    tool = get_registry().get("run_gst_reconciliation")
    assert requires_confirmation(tool.descriptor) is True


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__]))
