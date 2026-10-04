"""Opt-in OpenAI reasoning-field transport for legacy inline-thinking clients.

Only explicit ``openai-chat-thinking`` routes select this adapter. Ordinary
OpenAI traffic stays byte-for-byte pass-through. Streaming reasoning/answer text
is moved, never generated, repaired or interpreted; only legacy delimiters are
added. Unary responses retain separate reasoning and answer fields: the pinned
client parses their content directly as JSON without stripping thinking tags.
"""
from copy import deepcopy

from .native import NativeJsonWire
from defuzex_model_interceptor.transport.json import json_bytes
from defuzex_model_interceptor.transport.sse import SSEDecoder


def _text(value, name):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"Legacy thinking adapter requires string {name}")
    return value


def _choice(payload):
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or len(choices) > 1:
        raise ValueError("Legacy thinking adapter supports one choice")
    if not choices:
        return None
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("index", 0) != 0:
        raise ValueError("Legacy thinking adapter requires choice index zero")
    return choice


def _validate_message(message):
    if not isinstance(message, dict):
        raise ValueError("Legacy thinking adapter requires a message object")
    if message.get("tool_calls") or message.get("function_call"):
        raise ValueError("Legacy thinking adapter does not translate tool calls")
    reasoning = _text(message.get("reasoning_content"), "reasoning_content")
    content = _text(message.get("content"), "content")
    if reasoning and any(tag in reasoning or tag in content for tag in ("<think>", "</think>")):
        raise ValueError("Ambiguous mixed inline and separate thinking formats")
    return reasoning, content


class ThinkingChatWire(NativeJsonWire):
    passthrough = False
    stream_type = "text/event-stream"
    capture_client_stream = True
    response_adapter = "reasoning-content-to-inline-v1"

    def __init__(self):
        super().__init__("/chat/completions")
        # Not an automatic protocol signature: only explicit opted-in routes.
        self.signature = None

    def decode(self, request):
        source, payload = super().decode(request)
        if type(source.get("n", 1)) is not int or source.get("n", 1) != 1:
            raise ValueError("Legacy thinking adapter supports n=1 only")
        return source, payload

    def response(self, payload, status):
        # AIRA's streamed planning/reflection parses </think>, but its ainvoke
        # intention/relevancy checks parse content directly as JSON. Combining
        # unary reasoning with that answer breaks otherwise valid model JSON.
        # Preserve both fields and all errors/usage/finish metadata unchanged.
        return payload

    def stream(self):
        return ThinkingChatStream()


class ThinkingChatStream:
    def __init__(self):
        self.parser = SSEDecoder()
        self.phase = "initial"
        self.terminal_sent = False

    @staticmethod
    def _frame(event):
        return b"data: " + json_bytes(event) + b"\n\n"

    @staticmethod
    def _fragment(event, text):
        # Synthetic framing carries no usage, finish reason or model answer.
        result = {key: event[key] for key in (
            "id", "object", "created", "model", "system_fingerprint"
        ) if key in event}
        result["choices"] = [{"index": 0, "delta": {"content": text}, "finish_reason": None}]
        return result

    def feed(self, chunk):
        output = bytearray()
        for upstream in self.parser.feed(chunk):
            event = deepcopy(upstream)
            choice = _choice(event)
            if choice is None:
                output.extend(self._frame(event))
                continue
            delta = choice.get("delta", {})
            reasoning, content = _validate_message(delta)
            if reasoning:
                if self.phase == "answer":
                    raise ValueError("Reasoning after answer cannot be serialized as legacy thinking")
                prefix = "<think>" if self.phase == "initial" else ""
                self.phase = "reasoning"
                if content:
                    output.extend(self._frame(self._fragment(event, prefix + reasoning)))
                else:
                    delta["content"] = prefix + reasoning
                delta.pop("reasoning_content", None)
            if content:
                if self.phase == "reasoning":
                    if "<think>" in content or "</think>" in content:
                        raise ValueError("Ambiguous mixed inline and separate thinking formats")
                    # Dedicated chunk matches the native streaming client's marker handling.
                    output.extend(self._frame(self._fragment(event, "</think>")))
                self.phase = "answer"
            output.extend(self._frame(event))
        if self.parser.done and not self.terminal_sent:
            output.extend(b"data: [DONE]\n\n")
            self.terminal_sent = True
        return bytes(output)
