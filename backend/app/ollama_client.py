"""Bounded non-streaming client for a fixed local Ollama service; never pulls."""

import http.client
import json
import socket
import threading
import time
from contextlib import suppress
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.agent_schemas import CONTEXT_TOKENS, MODEL

MAX_RESPONSE_BYTES = 65_536
PREDICT_TOKENS = 384


class OllamaUnavailable(Exception):
    pass


class OllamaTimeout(Exception):
    pass


class OllamaProtocolError(Exception):
    pass


class FunctionCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any]


class ToolCall(BaseModel):
    function: FunctionCall


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str = Field(default="", max_length=5000)
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=16)


class OllamaReply(BaseModel):
    model: Literal["qwen3:4b-instruct"]
    message: AssistantMessage
    done: Literal[True]
    done_reason: str
    prompt_eval_count: int = Field(ge=0, strict=True)


class OllamaClient:
    def chat(
        self, messages: list[dict], tools: list[dict], *, timeout: float
    ) -> OllamaReply:
        connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout)
        deadline = time.monotonic() + timeout
        watchdog = None
        try:
            connection.connect()
            transport = connection.sock

            def abort() -> None:
                if transport is not None:
                    with suppress(OSError):
                        transport.shutdown(socket.SHUT_RDWR)

            watchdog = threading.Timer(max(0.001, deadline - time.monotonic()), abort)
            watchdog.daemon = True
            watchdog.start()
            connection.request(
                "POST",
                "/api/chat",
                body=json.dumps(
                    {
                        "model": MODEL,
                        "messages": messages,
                        "tools": tools,
                        "stream": False,
                        "think": False,
                        "keep_alive": "5m",
                        "options": {
                            "num_ctx": CONTEXT_TOKENS,
                            "num_predict": PREDICT_TOKENS,
                            "temperature": 0,
                        },
                    }
                ).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            if response.status in {404, 503}:
                raise OllamaUnavailable
            if response.status != 200:
                raise OllamaProtocolError
            data = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise OllamaTimeout
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(4096, MAX_RESPONSE_BYTES + 1 - len(data)))
                data.extend(chunk)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise OllamaProtocolError
                if not chunk:
                    break
            reply = OllamaReply.model_validate_json(data)
            if (
                reply.done_reason != "stop"
                or reply.prompt_eval_count > CONTEXT_TOKENS - PREDICT_TOKENS
            ):
                raise OllamaProtocolError
            return reply
        except TimeoutError as error:
            raise OllamaTimeout from error
        except (OSError, http.client.HTTPException) as error:
            if time.monotonic() >= deadline:
                raise OllamaTimeout from error
            raise OllamaUnavailable from error
        except ValidationError as error:
            raise OllamaProtocolError from error
        finally:
            if watchdog is not None:
                watchdog.cancel()
            connection.close()
