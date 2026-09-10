"""Controlled TLS upstream. Test-only; never imported by production packages."""
import json
import ipaddress
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

TEXT = "中文\u2028流式\u2029 OK"

def start(directory):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
            .not_valid_after(now+timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(key, hashes.SHA256()))
    pem, private = directory / "upstream.pem", directory / "upstream.key"
    pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    private.chmod(0o600)
    seen = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            seen.append({"path": self.path, "payload": body,
                         "auth_replaced": self.headers.get("authorization") == "Bearer lab-upstream-secret",
                         "google_key_removed": not self.headers.get("x-goog-api-key")})
            if body.get("model") != "lab/target" or not seen[-1]["auth_replaced"]:
                self.send_error(401)
                return
            marker = json.dumps(body)
            if "LAB:SLOW" in marker:
                time.sleep(0.5)
            if "LAB:429" in marker:
                data = b'{"error":{"message":"controlled rate limit"}}'
                self.send_response(429)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            payload, events = make_response(self.path, body["model"])
            if "LAB:INCOMPLETE" in marker:
                events = events[:1]
            if "LAB:STREAM_ERROR" in marker:
                events = events[:1] + [{"error": {"message": "controlled stream error"}}]
            self.send_response(200)
            if not body.get("stream"):
                data = json.dumps(payload, ensure_ascii=False).encode()
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_header("content-type", "text/event-stream")
            self.send_header("transfer-encoding", "chunked")
            self.end_headers()
            for index, event in enumerate(events):
                if index:
                    time.sleep(0.18)  # Assert a client receives text before EOF.
                data = (("data: " + json.dumps(event, ensure_ascii=False)) if isinstance(event, dict) else "data: " + event).encode() + b"\r\n\r\n"
                if isinstance(event, dict) and "type" in event:
                    data = b"event: " + event["type"].encode() + b"\r\n" + data
                # Split within Unicode codepoints and SSE delimiters.
                for offset in range(0, len(data), 7):
                    part = data[offset:offset+7]
                    self.wfile.write(f"{len(part):x}\r\n".encode() + part + b"\r\n")
                    self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

    server = ThreadingHTTPServer(("0.0.0.0", 8443), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(pem, private)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, pem, seen

def make_response(path, model):
    usage = {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}
    if path.endswith("/messages"):
        response = {"id": "msg_lab", "type": "message", "role": "assistant", "model": model,
                    "content": [{"type": "text", "text": TEXT}], "stop_reason": "end_turn", "stop_sequence": None,
                    "usage": {"input_tokens": 3, "output_tokens": 4}}
        events = [{"type": "message_start", "message": dict(response, content=[], stop_reason=None)},
                  {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                  {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": TEXT[:2]}},
                  {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": TEXT[2:]}},
                  {"type": "content_block_stop", "index": 0},
                  {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 4}},
                  {"type": "message_stop"}]
    elif path.endswith("/responses"):
        response = {"id": "resp_lab", "object": "response", "created_at": 1, "status": "completed", "model": model,
                    "output": [{"id": "msg_lab", "type": "message", "role": "assistant", "status": "completed",
                                "content": [{"type": "output_text", "text": TEXT, "annotations": []}]}],
                    "usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7}}
        events = [{"type": "response.created", "response": dict(response, status="in_progress", output=[]), "sequence_number": 0},
                  {"type": "response.output_text.delta", "delta": TEXT[:2], "item_id": "msg_lab", "output_index": 0, "content_index": 0, "sequence_number": 1},
                  {"type": "response.output_text.delta", "delta": TEXT[2:], "item_id": "msg_lab", "output_index": 0, "content_index": 0, "sequence_number": 2},
                  {"type": "response.completed", "response": response, "sequence_number": 3}]
    else:
        base = {"id": "chatcmpl-lab", "object": "chat.completion.chunk", "created": 1, "model": model}
        response = dict(base, object="chat.completion", choices=[{"index": 0, "message": {"role": "assistant", "content": TEXT}, "finish_reason": "stop"}], usage=usage)
        events = [dict(base, choices=[{"index": 0, "delta": {"role": "assistant", "content": TEXT[:2]}, "finish_reason": None}]),
                  dict(base, choices=[{"index": 0, "delta": {"content": TEXT[2:]}, "finish_reason": None}]),
                  dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}]),
                  dict(base, choices=[], usage=usage), "[DONE]"]
    return response, events
