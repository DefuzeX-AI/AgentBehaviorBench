"""Ollama text chat/generate semantics over OpenRouter chat completions."""
from datetime import datetime, timezone
from .sse import SSEDecoder


class OllamaWire:
    def __init__(self, generate=False):
        self.generate = generate
        self.source_model = None
        self.streaming = True

    endpoint = "/chat/completions"
    response_type = "application/json"
    stream_type = "application/x-ndjson"

    def decode(self, request):
        from . import json_request
        source = json_request(request)
        allowed = {"model", "prompt", "system", "messages", "stream", "options", "keep_alive", "tools"}
        if source.get("tools"):
            raise ValueError("Ollama tool translation is not supported")
        if set(source) - allowed:
            raise ValueError("Unsupported Ollama fields: " + ", ".join(sorted(set(source) - allowed)))
        self.source_model = source.get("model")
        self.streaming = source.get("stream", True)
        options = source.get("options", {})
        mapping = {"num_predict": "max_tokens", "temperature": "temperature", "top_p": "top_p",
                   "stop": "stop", "seed": "seed", "presence_penalty": "presence_penalty",
                   "frequency_penalty": "frequency_penalty"}
        if set(options) - mapping.keys():
            raise ValueError("Unsupported Ollama generation options")
        messages = source.get("messages", [])
        if self.generate:
            messages = ([{"role": "system", "content": source["system"]}] if source.get("system") else [])
            messages += [{"role": "user", "content": source.get("prompt", "")}]
        for message in messages:
            if set(message) - {"role", "content"} or not isinstance(message.get("content"), str):
                raise ValueError("Only text Ollama messages are supported")
        if not messages:
            raise ValueError("Ollama messages are required")
        payload = {"messages": messages, "stream": self.streaming, **{mapping[k]: v for k,v in options.items()}}
        if self.streaming:
            payload["stream_options"] = {"include_usage": True}
        return source, payload

    def translate(self, payload, done=False):
        if payload.get("error"):
            raise ValueError("Upstream returned an error")
        choices = payload.get("choices", [])
        if len(choices) > 1:
            raise ValueError("Ollama requires one candidate")
        choice = choices[0] if choices else {}
        message = choice.get("message", choice.get("delta", {}))
        if message.get("tool_calls") or message.get("function_call"):
            raise ValueError("Ollama tool translation is not supported")
        result = {"model": payload.get("model", self.source_model),
                  "created_at": datetime.now(timezone.utc).isoformat(), "done": done}
        text = message.get("content") or ""
        if self.generate:
            result["response"] = text
        else:
            result["message"] = {"role": "assistant", "content": text}
        if done:
            result["done_reason"] = choice.get("finish_reason") or "stop"
            usage = payload.get("usage", {})
            result.update(prompt_eval_count=usage.get("prompt_tokens", 0),
                          eval_count=usage.get("completion_tokens", 0))
        return result

    def response(self, payload, status):
        if status >= 400:
            return {"error": str(payload.get("error", "Upstream failure"))}
        return self.translate(payload, done=True)

    def stream(self):
        return OllamaStream(self)


class OllamaStream:
    def __init__(self, wire):
        self.wire = wire
        self.parser = SSEDecoder()
        self.last = {}
        self.finish_reason = None
        self.emitted_done = False

    def feed(self, chunk):
        from . import json_bytes
        output = bytearray()
        for event in self.parser.feed(chunk):
            self.last.update({k:v for k,v in event.items() if k != "choices"})
            choices = event.get("choices", [])
            if choices:
                self.finish_reason = choices[0].get("finish_reason") or self.finish_reason
                # NDJSON clients may use Unicode-aware splitlines(). Escapes
                # preserve U+0085/U+2028/U+2029 without creating record breaks.
                output.extend(json_bytes(self.wire.translate(event), ascii_only=True) + b"\n")
        if self.parser.done and not self.emitted_done:
            terminal = dict(self.last, choices=[{"finish_reason": self.finish_reason, "delta": {}}])
            output.extend(json_bytes(self.wire.translate(terminal, done=True), ascii_only=True) + b"\n")
            self.emitted_done = True
        return bytes(output)
