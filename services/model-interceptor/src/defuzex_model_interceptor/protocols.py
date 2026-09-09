"""Built-in model HTTP payload decoders."""

from __future__ import annotations

import json


class JsonHttpProtocol:
    name = "json-http"

    def decode_request(self, content: bytes, content_type: str) -> object:
        return _decode(content, content_type)

    def decode_response(self, content: bytes, content_type: str) -> object:
        return _decode(content, content_type)


class OpenAIChatProtocol(JsonHttpProtocol):
    name = "openai-chat"


class OpenAIResponsesProtocol(JsonHttpProtocol):
    name = "openai-responses"


class AnthropicMessagesProtocol(JsonHttpProtocol):
    name = "anthropic-messages"


def _decode(content: bytes, content_type: str) -> object:
    text = content.decode("utf-8", errors="replace")
    if "text/event-stream" in content_type.lower():
        events: list[object] = []
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            value = line[5:].strip()
            if not value or value == "[DONE]":
                continue
            try:
                events.append(json.loads(value))
            except json.JSONDecodeError:
                events.append(value)
        return {"events": events}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}


JSON_HTTP_PROTOCOL = JsonHttpProtocol()
OPENAI_CHAT_PROTOCOL = OpenAIChatProtocol()
OPENAI_RESPONSES_PROTOCOL = OpenAIResponsesProtocol()
ANTHROPIC_MESSAGES_PROTOCOL = AnthropicMessagesProtocol()


class GeminiContentProtocol(JsonHttpProtocol):
    name = "gemini-content"


GEMINI_CONTENT_PROTOCOL = GeminiContentProtocol()
