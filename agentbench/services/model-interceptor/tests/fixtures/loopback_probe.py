"""Non-root socket probes, executed inside the production interceptor namespace."""
import errno
import os
import socket
import threading
import unittest
from urllib.request import ProxyHandler, build_opener
from http.server import BaseHTTPRequestHandler, HTTPServer


class NativeLoopbackTest(unittest.TestCase):
    def test_tcp_and_udp_on_random_ports(self):
        for family, host in ((socket.AF_INET, "127.0.0.1"),
                             (socket.AF_INET, "127.0.0.2"), (socket.AF_INET6, "::1")):
            for server_first in (False, True):
                with self.subTest(host=host, server_first=server_first):
                    with socket.socket(family) as server:
                        server.bind((host, 0))
                        server.listen()
                        server.settimeout(3)

                        def serve():
                            with server.accept()[0] as connection:
                                connection.settimeout(3)
                                if server_first:
                                    connection.sendall(b"greeting")
                                else:
                                    connection.sendall(connection.recv(64))

                        worker = threading.Thread(target=serve, daemon=True)
                        worker.start()
                        with socket.socket(family) as client:
                            client.settimeout(2)
                            client.connect(server.getsockname())
                            if not server_first:
                                client.sendall(b"PING\r\n")
                            self.assertEqual(client.recv(64), b"greeting" if server_first else b"PING\r\n")
                        worker.join(4)
            with self.subTest(host=host, transport="udp"):
                with socket.socket(family, socket.SOCK_DGRAM) as server, socket.socket(family, socket.SOCK_DGRAM) as client:
                    server.bind((host, 0))
                    server.settimeout(2)
                    client.settimeout(2)
                    client.sendto(b"probe", server.getsockname())
                    data, peer = server.recvfrom(64)
                    server.sendto(data, peer)
                    self.assertEqual(client.recv(64), b"probe")

    def test_closed_ports_really_refuse(self):
        for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
            with self.subTest(host=host), socket.socket(family) as reserved:
                reserved.bind((host, 0))  # Reserved, but deliberately not listening.
                with socket.socket(family) as client:
                    client.settimeout(2)
                    self.assertEqual(client.connect_ex(reserved.getsockname()), errno.ECONNREFUSED)

    def test_undeclared_http_random_port(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"local")

            def log_message(self, *args):
                pass

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with build_opener(ProxyHandler({})).open(
                        f"http://127.0.0.1:{server.server_port}/random", timeout=2) as response:
                    self.assertEqual(response.read(), b"local")
            finally:
                server.shutdown()
                worker.join(3)

    def test_external_http_still_reaches_policy(self):
        # The isolated bridge gateway is routable but outside this namespace.
        # The proxy must deny it before attempting any upstream connection.
        host = os.environ["ABB_EXTERNAL_TEST_HOST"]
        with socket.create_connection((host, 18080), timeout=2) as client:
            client.sendall(f"GET / HTTP/1.1\r\nHost: {host}:18080\r\nConnection: close\r\n\r\n".encode())
            self.assertIn(b"403", client.recv(4096).split(b"\r\n")[0])

    def test_external_udp_is_rejected(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(2)
            with self.assertRaises(OSError) as caught:
                client.sendto(b"probe", (os.environ["ABB_EXTERNAL_TEST_HOST"], 18080))
            self.assertNotIsInstance(caught.exception, TimeoutError)

    def test_docker_dns_still_works(self):
        name = socket.gethostname()
        self.assertTrue(socket.getaddrinfo(name, 80))
        # Exercise Docker's UDP DNS listener without depending on public DNS.
        query = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x09localhost\x00\x00\x01\x00\x01"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(2)
            client.sendto(query, ("127.0.0.11", 53))
            self.assertEqual(client.recv(4096)[:2], b"\x12\x34")


if __name__ == "__main__":
    unittest.main(verbosity=2)
