"""Incremental SSE framing; retain UTF-8 bytes until an entire event arrives."""
import json


class SSEDecoder:
    def __init__(self, terminal="done", maximum=4 * 1024 * 1024):
        self.buffer = bytearray()
        self.terminal = terminal
        self.maximum = maximum
        self.done = False

    def feed(self, chunk):
        self.buffer.extend(chunk)
        self.buffer[:] = self.buffer.replace(b"\r\n", b"\n")
        events = []
        while b"\n\n" in self.buffer:
            frame, _, rest = self.buffer.partition(b"\n\n")
            self.buffer[:] = rest
            if len(frame) > self.maximum:
                raise ValueError("SSE event exceeds supported size")
            data = b"\n".join(line[5:].removeprefix(b" ") for line in frame.split(b"\n") if line.startswith(b"data:"))
            if not data:
                continue
            if data == b"[DONE]":
                if self.terminal != "done" and not self.done:
                    raise ValueError("Missing native stream terminal event")
                self.done = True
                continue
            if self.done:
                raise ValueError("Data after terminal SSE event")
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError("SSE payload must be an object")
            if value.get("error") or value.get("type") in {"error", "response.failed", "response.incomplete"}:
                raise ValueError("Upstream stream reported an error")
            if value.get("type") == self.terminal:
                self.done = True
            events.append(value)
        if len(self.buffer) > self.maximum:
            raise ValueError("SSE event exceeds supported size")
        if not chunk and (self.buffer.strip() or not self.done):
            raise ValueError("Incomplete upstream stream")
        return events
