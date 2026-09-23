"""End-to-end proxy behavior against a local upstream; no external network."""
import asyncio
import unittest
from unittest.mock import patch

from defuzex_egress_observer import proxy as proxy_module
from defuzex_egress_observer.config import ObserverConfig
from defuzex_egress_observer.policy import AllowList, AllowRule
from defuzex_egress_observer.proxy import EgressProxy, parse_head


class ParseHeadTest(unittest.TestCase):
    def test_connect_and_absolute_form(self):
        self.assertEqual(parse_head(b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n"), ("CONNECT", "pypi.org", 443, None))
        self.assertEqual(parse_head(b"CONNECT [::1]:8443 HTTP/1.1\r\n\r\n"), ("CONNECT", "::1", 8443, None))
        self.assertEqual(parse_head(b"GET http://deb.debian.org/debian/x?y=1 HTTP/1.1\r\n\r\n"),
                         ("GET", "deb.debian.org", 80, "/debian/x"))

    def test_origin_form_and_bad_lines_are_rejected(self):
        for head in (b"GET /x HTTP/1.1\r\n\r\n", b"CONNECT pypi.org HTTP/1.1\r\n\r\n",
                     b"GET http://h/ HTTP/2\r\n\r\n", b"garbage\r\n\r\n"):
            with self.subTest(head=head), self.assertRaises(ValueError):
                parse_head(head)


class ProxyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        patcher = patch.object(proxy_module.events, "emit",
                               side_effect=lambda name, **data: self.events.append((name, data)))
        patcher.start()
        self.addCleanup(patcher.stop)

        async def upstream(reader, writer):
            data = await reader.read(65536)
            if data.startswith(b"GET "):
                writer.write(b"HTTP/1.1 204 No Content\r\ncontent-length: 0\r\nconnection: close\r\n\r\n")
            else:
                writer.write(b"echo:" + data)
            await writer.drain()
            writer.close()

        self.upstream = await asyncio.start_server(upstream, "127.0.0.1", 0)
        self.upstream_port = self.upstream.sockets[0].getsockname()[1]
        config = ObserverConfig(agent_id="agent", listen_port=0,
                                allow=AllowList((AllowRule("127.0.0.1", (self.upstream_port,)),)))
        self.server = await asyncio.start_server(EgressProxy(config).handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        for server in (self.server, self.upstream):
            server.close()
            await server.wait_closed()

    async def exchange(self, payload: bytes) -> bytes:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(payload)
        await writer.drain()
        data = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.05)
        return data

    async def test_allowed_tunnel_is_relayed_and_recorded(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(f"CONNECT 127.0.0.1:{self.upstream_port} HTTP/1.1\r\n\r\n".encode())
        await writer.drain()
        self.assertEqual(await reader.readuntil(b"\r\n\r\n"), b"HTTP/1.1 200 Connection Established\r\n\r\n")
        writer.write(b"hello")
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(), 5), b"echo:hello")
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.05)
        names = [name for name, _ in self.events]
        self.assertEqual(names, ["egress_request", "egress_response"])
        done = self.events[-1][1]
        self.assertEqual((done["host"], done["method"], done["status"]), ("127.0.0.1", "CONNECT", 200))
        self.assertEqual((done["bytes_up"], done["bytes_down"]), (5, 10))
        self.assertTrue(done["conn_id"].startswith("egress_"))
        self.assertNotIn("call_id", done)

    async def test_unlisted_destination_is_denied_and_recorded(self):
        data = await self.exchange(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
        self.assertTrue(data.startswith(b"HTTP/1.1 403 "))
        self.assertEqual([name for name, _ in self.events], ["egress_denied"])
        denied = self.events[0][1]
        self.assertEqual((denied["host"], denied["port"], denied["error_code"]), ("example.com", 443, "egress_denied"))

    async def test_plain_http_request_is_forwarded_with_its_status(self):
        data = await self.exchange(
            f"GET http://127.0.0.1:{self.upstream_port}/pkg?token=x HTTP/1.1\r\nhost: 127.0.0.1\r\n\r\n".encode())
        self.assertTrue(data.startswith(b"HTTP/1.1 204 "))
        done = self.events[-1][1]
        self.assertEqual((done["path"], done["status"]), ("/pkg", 204))

    async def test_malformed_request_is_rejected(self):
        data = await self.exchange(b"GET /relative HTTP/1.1\r\n\r\n")
        self.assertTrue(data.startswith(b"HTTP/1.1 400 "))
        self.assertEqual(self.events[0][0], "egress_error")

    async def test_unreachable_upstream_is_a_bad_gateway(self):
        self.upstream.close()
        await self.upstream.wait_closed()
        data = await self.exchange(f"CONNECT 127.0.0.1:{self.upstream_port} HTTP/1.1\r\n\r\n".encode())
        self.assertTrue(data.startswith(b"HTTP/1.1 502 "))
        self.assertEqual(self.events[0][1]["error_code"], "connect_failed")


if __name__ == "__main__":
    unittest.main()
