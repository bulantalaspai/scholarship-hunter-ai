import json
from unittest.mock import Mock

import pytest

from backend.app import ollama_client
from backend.app.ollama_client import (
    OllamaClient,
    OllamaProtocolError,
    OllamaTimeout,
    OllamaUnavailable,
)


class Response:
    def __init__(self, body, status=200):
        self.status = status
        self.body = body

    def read1(self, amount):
        result, self.body = self.body[:amount], self.body[amount:]
        return result


def connection(monkeypatch, body=None, status=200):
    if body is None:
        body = json.dumps(
            {
                "model": "qwen3:4b-instruct",
                "message": {
                    "role": "assistant",
                    "content": '{"recommendation_ids":[]}',
                },
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 1000,
            }
        ).encode()
    client = Mock()
    client.getresponse.return_value = Response(body, status)
    factory = Mock(return_value=client)
    monkeypatch.setattr(ollama_client.http.client, "HTTPConnection", factory)
    return client, factory


def test_transport_only_calls_fixed_local_chat_without_pull_or_cloud(monkeypatch):
    client, factory = connection(monkeypatch)
    reply = OllamaClient().chat([{"role": "user", "content": "Test"}], [], timeout=2)
    factory.assert_called_once_with("127.0.0.1", 11434, timeout=2)
    args, kwargs = client.request.call_args
    assert args == ("POST", "/api/chat")
    body = json.loads(kwargs["body"])
    assert body["model"] == "qwen3:4b-instruct"
    assert body["options"]["num_ctx"] == 4096
    assert body["stream"] is False and body["think"] is False
    assert reply.message.content == '{"recommendation_ids":[]}'
    client.close.assert_called_once()


@pytest.mark.parametrize("status", [404, 503])
def test_missing_model_or_service_is_unavailable(monkeypatch, status):
    connection(monkeypatch, status=status)
    with pytest.raises(OllamaUnavailable):
        OllamaClient().chat([], [], timeout=2)


@pytest.mark.parametrize(
    "body", [b"not JSON", b"{}", b'{"message":{"role":"system"}}', b"x" * 65_537]
)
def test_malformed_or_oversized_response_is_not_accepted(monkeypatch, body):
    connection(monkeypatch, body=body)
    with pytest.raises(OllamaProtocolError):
        OllamaClient().chat([], [], timeout=2)


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "other-model"},
        {"done": False},
        {"done_reason": "length"},
        {"prompt_eval_count": 4096},
    ],
)
def test_wrong_model_incomplete_output_and_context_truncation_fail_closed(
    monkeypatch, changes
):
    body = {
        "model": "qwen3:4b-instruct",
        "message": {"content": "{}"},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 1000,
    } | changes
    connection(monkeypatch, body=json.dumps(body).encode())
    with pytest.raises(OllamaProtocolError):
        OllamaClient().chat([], [], timeout=2)


@pytest.mark.parametrize(
    "missing", ["model", "done", "done_reason", "prompt_eval_count"]
)
def test_missing_wire_metadata_is_rejected(monkeypatch, missing):
    body = {
        "model": "qwen3:4b-instruct",
        "message": {"content": "{}"},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 1000,
    }
    del body[missing]
    connection(monkeypatch, body=json.dumps(body).encode())
    with pytest.raises(OllamaProtocolError):
        OllamaClient().chat([], [], timeout=2)


@pytest.mark.parametrize(
    ("error", "expected"),
    [(TimeoutError(), OllamaTimeout), (ConnectionRefusedError(), OllamaUnavailable)],
)
def test_local_connection_errors_are_safe(monkeypatch, error, expected):
    client, _ = connection(monkeypatch)
    client.connect.side_effect = error
    with pytest.raises(expected):
        OllamaClient().chat([], [], timeout=2)
    client.close.assert_called_once()
