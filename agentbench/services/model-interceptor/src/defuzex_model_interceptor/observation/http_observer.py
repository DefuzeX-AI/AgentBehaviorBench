"""Observe-only: capture copies, return each original stream chunk unchanged."""
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .body import prepare_body
SENSITIVE = ("authorization", "cookie", "key", "token", "secret", "password")


class HTTPObserver:
    def __init__(self, directory, *, limit, secrets=()):
        if limit <= 0:
            raise ValueError("Capture limit must be positive")
        self.directory = Path(directory)
        self.limit = limit
        self.secrets = set(secrets)

    def safe(self, data):
        for secret in sorted(self.secrets, key=len, reverse=True):
            if secret:
                raw = secret.encode()
                data = data.replace(raw, b"*" * len(raw))
        return data

    def journal(self, identity, kind, payload):
        line = json.dumps({"event_id": identity, "kind": kind, "payload": payload}) + "\n"
        with (self.directory / "live.jsonl").open("ab", buffering=0) as stream:
            stream.write(self.safe(line.encode()))

    def headers(self, headers):
        return {k: "[REDACTED]" if any(s in k.lower() for s in SENSITIVE) else v
                for k, v in headers.items()}

    def request(self, flow):
        for key, value in flow.request.headers.items():
            if any(s in key.lower() for s in SENSITIVE):
                self.secrets.add(value)
                if value.lower().startswith("bearer "):
                    self.secrets.add(value[7:])
        url = urlsplit(flow.request.pretty_url)
        query = []
        for key, value in parse_qsl(url.query, keep_blank_values=True):
            if any(s in key.lower() for s in SENSITIVE):
                self.secrets.add(value)
                value = "[REDACTED]"
            query.append((key, value))
        flow.metadata["capture"] = {
            **flow.metadata.get("model_selection", {}),
            "request_id": flow.id, "method": flow.request.method,
            "url": urlunsplit((url.scheme, url.netloc, url.path, urlencode(query), "")),
            "request_headers": self.headers(flow.request.headers),
            "started": time.monotonic(), "observed_time": datetime.now(UTC).isoformat(),
            "chunks": [], "received_bytes": 0, "buffer": bytearray(),
        }
        body = flow.request.content or b""
        (self.directory / (flow.id + ".request")).write_bytes(self.safe(body[:self.limit]))
        self.journal(flow.id + ":request", "network.native_request", {
            k: v for k,v in flow.metadata["capture"].items() if k not in ("started", "buffer", "chunks")})

    def responseheaders(self, flow):
        if "capture" not in flow.metadata:
            return
        capture = flow.metadata["capture"]
        capture["response_headers"] = self.headers(flow.response.headers)
        capture["status"] = flow.response.status_code
        capture["content_encoding"] = flow.response.headers.get("content-encoding", "identity")
        # ABB needs the complete body to translate non-streaming model replies.
        if flow.metadata.get("model_intercepted") and not callable(flow.response.stream):
            return
        previous = flow.response.stream if callable(flow.response.stream) else None
        def stream(chunk):
            forwarded = previous(chunk) if previous else chunk
            pieces = [forwarded] if isinstance(forwarded, bytes) else list(forwarded)
            for piece in pieces:
                capture_chunk(piece)
            return forwarded if isinstance(forwarded, bytes) else pieces

        def capture_chunk(chunk):
            if chunk:
                offset = capture["received_bytes"]
                capture["received_bytes"] += len(chunk)
                if len(capture["chunks"]) < 50000:
                    capture["chunks"].append({"chunk_seq": len(capture["chunks"]), "offset": offset,
                        "length": len(chunk), "observed_time": datetime.now(UTC).isoformat(),
                        "elapsed_ms": (time.monotonic() - capture["started"]) * 1000})
                    self.journal(flow.id + ":chunk:" + str(len(capture["chunks"])), "network.chunk",
                                 {"request_id": flow.id, **capture["chunks"][-1]})
                if len(capture["buffer"]) < self.limit:
                    capture["buffer"].extend(chunk[:self.limit - len(capture["buffer"])])
        flow.response.stream = stream

    def finish(self, flow, complete):
        capture = flow.metadata.pop("capture", None)
        if not capture:
            return
        body = bytes(capture.pop("buffer"))
        capture["duration_ms"] = (time.monotonic() - capture.pop("started")) * 1000
        capture["complete"] = complete and capture["received_bytes"] <= self.limit
        capture["source"] = "native_outbound"
        evidence = prepare_body(body, encoding=capture.get("content_encoding", "identity"),
                                limit=self.limit, complete=capture["complete"], redact=self.safe)
        capture.update(evidence.metadata)
        capture["complete"] = evidence.complete
        (self.directory / (flow.id + ".response")).write_bytes(evidence.body)
        temporary = self.directory / (flow.id + ".partial")
        temporary.write_bytes(self.safe(json.dumps(capture).encode()))
        temporary.replace(self.directory / (flow.id + ".json"))

    def response(self, flow):
        capture = flow.metadata.get("capture")
        if capture is not None and not callable(flow.response.stream):
            body = flow.response.content or b""
            capture["buffer"].extend(body[:self.limit])
            capture["received_bytes"] = len(body)
            capture["status"] = flow.response.status_code
            capture["content_encoding"] = "identity"
        self.finish(flow, True)

    def error(self, flow):
        self.finish(flow, False)
