import json
from typing import Any

import httpx2
import pytest
from openai import OpenAI

from repair_agent.model import Limits, LiveAdapter


def test_official_sdk_request_and_structured_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-placeholder")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    captured: list[dict[str, Any]] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        captured.append(json.loads(request.content))
        action = {"tool": "read_source", "note": "Inspect editable source", "patch": None}
        return httpx2.Response(
            200,
            json={
                "id": "resp_test",
                "created_at": 0,
                "model": "gpt-6-luna",
                "object": "response",
                "status": "completed",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": json.dumps(action), "annotations": []}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 123,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 12,
                    "output_tokens_details": {"reasoning_tokens": 0},
                    "total_tokens": 135,
                },
            },
        )

    adapter = LiveAdapter()
    adapter.client.close()
    with httpx2.Client(transport=httpx2.MockTransport(handle)) as transport:
        adapter.client = OpenAI(
            api_key="local-test-placeholder", http_client=transport, max_retries=0
        )
        action, usage = adapter.choose({"allowed_tools": ["read_source"]}, Limits(), 5)
    assert action.tool == "read_source"
    assert usage == {"input_tokens": 123, "output_tokens": 12}
    body = captured[0]
    assert body["model"] == "gpt-6-luna"
    assert body["store"] is False
    assert body["max_output_tokens"] == 2200
    assert body["text"]["format"]["strict"] is True
    assert body["reasoning"]["effort"] == "low"
    assert not any("scripted" in str(value) for value in body.values())
