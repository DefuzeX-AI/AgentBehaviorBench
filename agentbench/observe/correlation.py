"""Scoped transport instrumentation; never infer causality from timestamps."""
from contextlib import contextmanager
from contextvars import ContextVar
from fnmatch import fnmatchcase
from importlib import import_module
from threading import RLock
from urllib.parse import urlsplit

HEADER = 'x-abb-framework-span'
current_span = ContextVar('abb_current_span', default=None)
_targets = ContextVar('abb_correlation_targets', default=None)
_lock = RLock()
_users = 0
_restorations = []
_hooks = {}


def register_transport(name, install):
    """Register a scoped installer accepting an idempotent patch function."""
    with _lock:
        if _users or name in _hooks:
            raise ValueError(f'Cannot register correlation transport: {name}')
        _hooks[name] = install


def _headers(url, headers):
    patterns = _targets.get()
    if patterns is None:
        return
    # Called for each wire request, including redirects; remove stale IDs.
    headers.pop(HEADER, None)
    span = current_span.get()
    host = urlsplit(str(url)).hostname or ''
    if span and any(fnmatchcase(host, pattern) for pattern in patterns):
        headers[HEADER] = span


def _httpx(module_name, patch):
    module = import_module(module_name)
    for cls, asynchronous in ((module.Client, False), (module.AsyncClient, True)):
        # Unlike send(), this seam runs for each redirected/retried wire request.
        original = cls._send_single_request
        def wrap(method, is_async):
            if is_async:
                async def send(self, request):
                    _headers(request.url, request.headers)
                    try:
                        return await method(self, request)
                    finally:
                        if _targets.get() is not None:
                            request.headers.pop(HEADER, None)
            else:
                def send(self, request):
                    _headers(request.url, request.headers)
                    try:
                        return method(self, request)
                    finally:
                        if _targets.get() is not None:
                            request.headers.pop(HEADER, None)
            return send
        patch(cls, '_send_single_request', wrap(original, asynchronous))


def _requests(patch):
    module = import_module('requests')
    original = module.Session.send
    def send(self, request, **kwargs):
        _headers(request.url, request.headers)
        try:
            return original(self, request, **kwargs)
        finally:
            if _targets.get() is not None:
                request.headers.pop(HEADER, None)
    patch(module.Session, 'send', send)


def _aiohttp(patch):
    module = import_module('aiohttp')
    original = module.ClientRequest.__init__
    def initialize(self, method, url, **kwargs):
        # ClientRequest is rebuilt for redirects and resolves base_url first.
        original(self, method, url, **kwargs)
        _headers(self.url, self.headers)
    patch(module.ClientRequest, '__init__', initialize)


register_transport('httpx', lambda patch: _httpx('httpx', patch))
register_transport('httpx2', lambda patch: _httpx('httpx2', patch))
register_transport('requests', _requests)
register_transport('aiohttp', _aiohttp)


@contextmanager
def model_correlation(host_patterns):
    """Nested/concurrent scopes share patches, but never scope data."""
    global _users
    token = _targets.set(tuple(host_patterns))
    span_token = current_span.set(current_span.get())
    supported = {}
    try:
        with _lock:
            if not _users:
                seen = set()
                def patch(cls, name, replacement):
                    key = (cls, name)
                    if key not in seen:
                        seen.add(key)
                        _restorations.append((cls, name, getattr(cls, name)))
                        setattr(cls, name, replacement)
                try:
                    for name, installer in _hooks.items():
                        try:
                            installer(patch)
                        except ModuleNotFoundError as exc:
                            if exc.name != name:
                                raise
                            supported[name] = 'not_installed'
                        else:
                            supported[name] = 'installed'
                except BaseException:
                    for cls, name, original in reversed(_restorations):
                        setattr(cls, name, original)
                    _restorations.clear()
                    raise
            _users += 1
        try:
            yield supported
        finally:
            with _lock:
                _users -= 1
                if not _users:
                    for cls, name, original in reversed(_restorations):
                        setattr(cls, name, original)
                    _restorations.clear()
    finally:
        current_span.reset(span_token)
        _targets.reset(token)
