from __future__ import annotations

import json

import pytest

from alphapredator_task_notifier.client import parse_mcp_payload


def test_parse_mcp_payload_prefers_structured_content_and_unwraps_result():
    raw = json.dumps({
        "result": "model-oriented text",
        "structuredContent": {"result": {"uuid": "task-1", "status": "PENDING"}},
    })
    assert parse_mcp_payload(raw) == {"uuid": "task-1", "status": "PENDING"}


def test_parse_mcp_payload_surfaces_mcp_error():
    with pytest.raises(RuntimeError, match="not connected"):
        parse_mcp_payload(json.dumps({"error": "not connected"}))
