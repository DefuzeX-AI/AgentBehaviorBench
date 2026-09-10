"""Carry framework span IDs to the local Interceptor, not to upstream providers.

Patches are scoped to the isolated worker and restored before process exit.
Only declared intercepted hosts receive the header. The proxy strips it before
forwarding both model and approved tool traffic.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from fnmatch import fnmatchcase
from urllib.parse import urlsplit

current_span = ContextVar("abb_current_span", default=None)


@contextmanager
def model_correlation(host_patterns):
    restorations = []

    def add_header(request):
        host = urlsplit(str(request.url)).hostname or ""
        span = current_span.get()
        if span and any(fnmatchcase(host, pattern) for pattern in host_patterns):
            request.headers["x-abb-framework-span"] = span

    try:
        try:
            import httpx
            original_async = httpx.AsyncClient.send
            original_sync = httpx.Client.send

            async def async_send(self, request, *args, **kwargs):
                add_header(request)
                return await original_async(self, request, *args, **kwargs)

            def sync_send(self, request, *args, **kwargs):
                add_header(request)
                return original_sync(self, request, *args, **kwargs)

            restorations.extend([(httpx.AsyncClient, "send", original_async), (httpx.Client, "send", original_sync)])
            httpx.AsyncClient.send, httpx.Client.send = async_send, sync_send
        except ImportError:
            pass
        try:
            import requests
            original_requests = requests.Session.send

            def requests_send(self, request, *args, **kwargs):
                add_header(request)
                return original_requests(self, request, *args, **kwargs)

            restorations.append((requests.Session, "send", original_requests))
            requests.Session.send = requests_send
        except ImportError:
            pass
        yield
    finally:
        for cls, name, method in reversed(restorations):
            setattr(cls, name, method)
