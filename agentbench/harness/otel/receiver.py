"""Case-local OTLP/HTTP and gRPC trace receivers."""
import base64
from concurrent.futures import ThreadPoolExecutor
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from threading import Thread

MAX_BATCH = 32 * 1024 * 1024


def protobuf_batch(request):
    from google.protobuf.json_format import MessageToDict
    doc = MessageToDict(request, use_integers_for_enums=True)
    for resource in doc.get("resourceSpans", []):
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                for item in [span, *span.get("links", [])]:
                    for key in ("traceId", "spanId", "parentSpanId"):
                        if key in item:
                            item[key] = base64.b64decode(item[key]).hex()
    doc.setdefault("resourceSpans", [])
    return doc


class BatchTooLarge(ValueError):
    pass


def _body(handler):
    transfer = handler.headers.get("Transfer-Encoding", "").lower()
    if transfer == "chunked":
        body = bytearray()
        while True:
            line = handler.rfile.readline(4096)
            if not line.endswith(b"\r\n"):
                raise ValueError("Invalid chunk size")
            size = int(line.split(b";", 1)[0].strip(), 16)
            if size < 0:
                raise ValueError("Invalid chunk size")
            if size > MAX_BATCH - len(body):
                raise BatchTooLarge()
            if not size:
                # The server closes this HTTP/1.0 connection after responding.
                return bytes(body)
            chunk = handler.rfile.read(size)
            if len(chunk) != size or handler.rfile.read(2) != b"\r\n":
                raise ValueError("Incomplete chunk")
            body.extend(chunk)
    if transfer:
        raise ValueError("Unknown transfer encoding")
    size = int(handler.headers.get("Content-Length", "-1"))
    if size < 0:
        raise ValueError("Missing content length")
    if size > MAX_BATCH:
        raise BatchTooLarge()
    body = handler.rfile.read(size)
    if len(body) != size:
        raise ValueError("Incomplete body")
    return body


class Receiver:
    def __init__(self, protocol, sink):
        self.protocol = protocol
        if protocol == "grpc":
            import grpc
            from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as messages, trace_service_pb2_grpc as service
            class Traces(service.TraceServiceServicer):
                def Export(self, request, context):
                    try:
                        sink.accept_json(protobuf_batch(request), transport="grpc")
                    except (ValueError, KeyError, TypeError) as exc:
                        sink.reject("Invalid OTLP trace export")
                        context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
                    return messages.ExportTraceServiceResponse()
            self.server = grpc.server(ThreadPoolExecutor(max_workers=2), options=[("grpc.max_receive_message_length", MAX_BATCH)])
            service.add_TraceServiceServicer_to_server(Traces(), self.server)
            port = self.server.add_insecure_port("127.0.0.1:0")
            self.server.start()
        else:
            class Handler(BaseHTTPRequestHandler):
                def do_POST(self):
                    if self.path != "/v1/traces":
                        self.send_error(404)
                        return
                    try:
                        body = _body(self)
                        if self.headers.get("Content-Encoding") == "gzip":
                            with gzip.GzipFile(fileobj=io.BytesIO(body)) as compressed:
                                body = compressed.read(MAX_BATCH + 1)
                            if len(body) > MAX_BATCH:
                                raise BatchTooLarge()
                        kind = self.headers.get_content_type()
                        if kind == "application/json":
                            doc = json.loads(body)
                            response = b"{}"
                        elif kind == "application/x-protobuf":
                            from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
                            from google.protobuf.message import DecodeError
                            try:
                                doc = protobuf_batch(ExportTraceServiceRequest.FromString(body))
                            except DecodeError as exc:
                                raise ValueError("Invalid OTLP protobuf") from exc
                            response = b""
                        else:
                            self.send_error(415)
                            return
                        sink.accept_json(doc, transport=kind)
                    except BatchTooLarge:
                        sink.reject("OTLP request exceeds the batch size limit")
                        self.send_error(413)
                        return
                    except (ValueError, KeyError, TypeError, EOFError, gzip.BadGzipFile):
                        sink.reject("Invalid OTLP trace export")
                        self.send_error(400)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", kind)
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)

                def log_message(self, *args):
                    pass

            self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            self.server.daemon_threads = False
            port = self.server.server_port
            self.thread = Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        self.endpoint = f"http://127.0.0.1:{port}"

    def close(self):
        if self.protocol == "grpc":
            self.server.stop(3).wait()
        else:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()
