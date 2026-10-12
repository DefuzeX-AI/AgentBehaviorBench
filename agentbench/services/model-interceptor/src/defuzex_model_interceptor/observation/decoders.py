"""Built-in model HTTP payload decoders."""

from __future__ import annotations

import json

from ..transport.sse import SSEDecoder


class JsonHttpProtocol:
    name = "json-http"
    stream_terminal = None

    def decode_request(self, content: bytes, content_type: str) -> object:
        return _decode(content, content_type)

    def decode_response(self, content: bytes, content_type: str) -> object:
        return _decode(content, content_type)

    def stream_complete(self, content: bytes, content_type: str) -> bool:
        if self.stream_terminal is None or 'text/event-stream' not in content_type.lower():
            return False
        parser = SSEDecoder(self.stream_terminal)
        try:
            parser.feed(content)
            parser.feed(b'')  # Require a complete final frame and no trailing partial data.
        except (ValueError, UnicodeError):
            return False
        return parser.done


class OpenAIChatProtocol(JsonHttpProtocol):
    name = "openai-chat"
    stream_terminal = "done"


class ThinkingChatProtocol(OpenAIChatProtocol):
    name = "openai-chat-thinking"


class OpenAIResponsesProtocol(JsonHttpProtocol):
    name = "openai-responses"
    stream_terminal = "response.completed"


class AnthropicMessagesProtocol(JsonHttpProtocol):
    name = "anthropic-messages"
    stream_terminal = "message_stop"


def _decode(content: bytes, content_type: str) -> object:
    text = content.decode("utf-8", errors="replace")
    if "text/event-stream" in content_type.lower():
        events: list[object] = []
        for frame in text.replace("\r\n", "\n").split("\n\n"):
            value = "\n".join(line[5:].removeprefix(" ") for line in frame.split("\n") if line.startswith("data:"))
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
THINKING_CHAT_PROTOCOL = ThinkingChatProtocol()
OPENAI_RESPONSES_PROTOCOL = OpenAIResponsesProtocol()
ANTHROPIC_MESSAGES_PROTOCOL = AnthropicMessagesProtocol()


class GeminiContentProtocol(JsonHttpProtocol):
    name = "gemini-content"


GEMINI_CONTENT_PROTOCOL = GeminiContentProtocol()
