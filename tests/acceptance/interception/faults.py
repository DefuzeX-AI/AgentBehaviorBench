"""Controlled-only failures. Never selected by the billable probe runner."""
import json
import os
import socket
import time
from google.ai.generativelanguage_v1beta import GenerativeServiceClient
from google.api_core import exceptions
import requests

def main():
    results = []
    def check(name, run):
        try:
            run()
            results.append({"case": name, "status": "passed"})
        except Exception as exc:
            results.append({"case": name, "status": "failed", "error": str(exc)})
    def expect(kind, run):
        try:
            run()
        except kind:
            return
        raise AssertionError("Expected " + kind.__name__)
    def rpc(prompt, *, streaming=False, token=None, timeout=5, extra=None):
        client = GenerativeServiceClient(client_options={"api_key": token or os.environ["GEMINI_API_KEY"]})
        request = {"model": "models/gemini", "contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        request.update(extra or {})
        try:
            if streaming:
                return list(client.stream_generate_content(request=request, retry=None, timeout=timeout))
            return client.generate_content(request=request, retry=None, timeout=timeout)
        finally:
            client.transport.close()
    check("grpc.bad-token", lambda: expect(exceptions.Unauthenticated, lambda: rpc("x", token="wrong")))
    check("grpc.unsupported-tools", lambda: expect(exceptions.InvalidArgument, lambda: rpc("x", extra={"tools": [{"function_declarations": [{"name": "foo"}]}]})))
    check("grpc.upstream-429", lambda: expect(exceptions.ResourceExhausted, lambda: rpc("LAB:429")))
    check("grpc.stream-error", lambda: expect(exceptions.InternalServerError, lambda: rpc("LAB:STREAM_ERROR", streaming=True)))
    check("grpc.incomplete-stream", lambda: expect(exceptions.InternalServerError, lambda: rpc("LAB:INCOMPLETE", streaming=True)))
    check("grpc.deadline", lambda: expect(exceptions.DeadlineExceeded, lambda: rpc("LAB:SLOW", timeout=0.1)))
    def cancel():
        with GenerativeServiceClient(client_options={"api_key": os.environ["GEMINI_API_KEY"]}) as client:
            stream = client.stream_generate_content(request={"model": "models/gemini", "contents": [{"parts": [{"text": "cancel"}]}]}, retry=None, timeout=5)
            assert next(stream).candidates
            assert stream.cancel()
    check("grpc.cancel", cancel)
    def concurrent():
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(rpc, ["parallel"] * 4))
        assert len(values) == 4 and all(value.candidates for value in values)
    check("grpc.concurrent", concurrent)
    def compressed():
        import grpc
        from google.ai.generativelanguage_v1beta.services.generative_service.transports.grpc import GenerativeServiceGrpcTransport
        channel = grpc.secure_channel("generativelanguage.googleapis.com:443", grpc.ssl_channel_credentials(), compression=grpc.Compression.Gzip)
        with GenerativeServiceClient(transport=GenerativeServiceGrpcTransport(channel=channel)) as client:
            value = client.generate_content(request={"model": "models/gemini", "contents": [{"parts": [{"text": "gzip " * 100}]}]},
                retry=None, timeout=5, metadata=(("x-goog-api-key", os.environ["GEMINI_API_KEY"]),))
            assert value.candidates
    check("grpc.gzip", compressed)
    def deny(url):
        response = requests.post(url, json={}, timeout=3)
        assert response.status_code == 403, response.status_code
    check("http.undeclared-path", lambda: deny("https://api.openai.com/v1/not-declared"))
    check("http.undeclared-port", lambda: deny("https://api.openai.com:8443/v1/chat/completions"))
    def udp():
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect(("127.0.0.2", 443))
            expect(OSError, lambda: (sock.send(b"not-http"), sock.recv(1)))
    check("network.udp-blocked", udp)
    def ipv6():
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            expect(OSError, lambda: sock.connect(("::1", 8443)))
    check("network.ipv6-blocked", ipv6)
    time.sleep(1)  # Allow cancelled upstream handlers and trace events to finish.
    result = {"matrix": results, "passed": sum(r["status"] == "passed" for r in results),
              "failed": sum(r["status"] == "failed" for r in results)}
    print(json.dumps(result))
    return bool(result["failed"])

if __name__ == "__main__":
    raise SystemExit(main())
