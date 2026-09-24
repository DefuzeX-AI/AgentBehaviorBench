"""HTTP forward proxy: ``CONNECT`` tunnels and absolute-form HTTP requests.

The model interceptor hands every request that matches neither a model route nor a
tool route to this proxy. It never decrypts a tunnel; it records the destination,
the decision and the transferred byte counts, which is enough to account for
non-model traffic separately from model calls.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit
from uuid import uuid4

from . import events
from .config import ObserverConfig

HEAD_LIMIT = 64 * 1024
CHUNK = 64 * 1024


class _BadRequest(ValueError):
    pass


def parse_head(head: bytes) -> tuple[str, str, int, str | None]:
    """Return ``(method, host, port, path)``; ``path`` is None for a tunnel."""
    try:
        line = head.split(b"\r\n", 1)[0].decode("ascii")
        method, target, version = line.split(" ")
    except (UnicodeDecodeError, ValueError) as exc:
        raise _BadRequest("Malformed request line") from exc
    if not version.startswith("HTTP/1."):
        raise _BadRequest("Unsupported HTTP version")
    if method == "CONNECT":
        host, sep, port = target.rpartition(":")
        host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
        if not sep or not host or not port.isdigit() or not 1 <= int(port) <= 65535:
            raise _BadRequest("Malformed CONNECT authority")
        return method, host, int(port), None
    url = urlsplit(target)
    if url.scheme != "http" or not url.hostname:
        raise _BadRequest("Only absolute-form http:// requests are forwarded")
    try:
        port = url.port or 80
    except ValueError as exc:
        raise _BadRequest("Malformed port") from exc
    return method, url.hostname, port, url.path or "/"


def _reply(writer: asyncio.StreamWriter, status: int, reason: str) -> None:
    body = reason.encode()
    writer.write(f"HTTP/1.1 {status} {reason}\r\ncontent-type: text/plain\r\n"
                 f"content-length: {len(body)}\r\nconnection: close\r\n\r\n".encode() + body)


def _status_code(first_bytes: bytes) -> int | None:
    parts = first_bytes.split(b"\r\n", 1)[0].split(b" ")
    return int(parts[1]) if len(parts) > 1 and parts[0].startswith(b"HTTP/") and parts[1].isdigit() else None


async def _pipe(source: asyncio.StreamReader, sink: asyncio.StreamWriter, counts: dict, key: str,
                first: list | None = None) -> None:
    try:
        while chunk := await source.read(CHUNK):
            if first is not None and not first:
                first.append(chunk)
            counts[key] += len(chunk)
            sink.write(chunk)
            await sink.drain()
        if sink.can_write_eof():
            sink.write_eof()
    except (ConnectionError, OSError):
        pass


async def _close(writer: asyncio.StreamWriter) -> None:
    writer.close()
    try:
        await writer.wait_closed()
    except (ConnectionError, OSError):
        pass


class EgressProxy:
    def __init__(self, config: ObserverConfig) -> None:
        self.config = config

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        conn_id = f"egress_{uuid4().hex}"
        started = time.monotonic()
        fields: dict[str, object] = {"agent_id": self.config.agent_id, "conn_id": conn_id}
        try:
            try:
                head = await reader.readuntil(b"\r\n\r\n")
                method, host, port, path = parse_head(head)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, _BadRequest) as exc:
                events.emit("egress_error", **fields, error_code="bad_request", error=str(exc)[:200])
                _reply(writer, 400, "Bad Request")
                return
            fields.update(method=method, host=host, port=port, path=path)
            rule = self.config.allow.match(host, port)
            if rule is None:
                events.emit("egress_denied", **fields, error_code="egress_denied", status=403)
                _reply(writer, 403, "Forbidden")
                return
            fields["rule"] = rule.host
            try:
                upstream_reader, upstream_writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), self.config.connect_timeout)
            except (OSError, asyncio.TimeoutError) as exc:
                events.emit("egress_error", **fields, error_code="connect_failed",
                            error=(type(exc).__name__ + ": " + str(exc))[:200])
                _reply(writer, 502, "Bad Gateway")
                return
            events.emit("egress_request", **fields)
            if path is None:
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                upstream_writer.write(head)
            counts = {"bytes_up": len(head) if path is not None else 0, "bytes_down": 0}
            first: list[bytes] = []
            await asyncio.gather(
                _pipe(reader, upstream_writer, counts, "bytes_up"),
                _pipe(upstream_reader, writer, counts, "bytes_down", first if path is not None else None))
            await _close(upstream_writer)
            events.emit("egress_response", **fields, **counts,
                        status=200 if path is None else _status_code(first[0] if first else b""),
                        duration_ms=round((time.monotonic() - started) * 1000, 3))
        finally:
            await _close(writer)

    async def serve(self, host: str = "0.0.0.0") -> asyncio.Server:
        return await asyncio.start_server(self.handle, host, self.config.listen_port, limit=HEAD_LIMIT)
