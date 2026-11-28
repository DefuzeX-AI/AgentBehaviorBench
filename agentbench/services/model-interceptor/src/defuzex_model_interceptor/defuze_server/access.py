"""Bounded, non-inference permission checks from the actual forwarding container."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_BYTES = 65_536


class AccessError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__('Defuze server permission check failed: ' + code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check(base_url, secret, *, opener=None):
    opener = opener or build_opener(ProxyHandler({}), NoRedirect())
    request = Request(base_url.rstrip('/') + '/chat/completions', method='OPTIONS',
                      headers={'Authorization': 'Bearer ' + secret, 'Accept': 'application/json'})
    started = time.monotonic()
    try:
        with opener.open(request, timeout=3) as response:
            if response.status != 200:
                raise AccessError('http_' + str(response.status))
            if ('POST' not in {v.strip() for v in response.headers.get('allow', '').split(',')}
                    or response.headers.get_content_type() != 'application/json'):
                raise AccessError('invalid_metadata')
            body = bytearray()
            while True:
                chunk = response.read1(min(8192, MAX_BYTES + 1 - len(body)))
                body.extend(chunk)
                if len(body) > MAX_BYTES or time.monotonic() - started > 5:
                    raise AccessError('response_limit')
                if not chunk:
                    break
            data = json.loads(body)
            if (not isinstance(data, dict) or data.get('name') != 'Sdk Agent Model'
                    or not isinstance(data.get('parses'), list) or 'application/json' not in data['parses']):
                raise AccessError('invalid_metadata')
    except HTTPError as exc:
        code = {401: 'unauthenticated', 403: 'forbidden'}.get(exc.code, 'http_' + str(exc.code))
        exc.close()
        raise AccessError(code) from None
    except (URLError, OSError, TimeoutError):
        raise AccessError('network_error') from None
    except (ValueError, RecursionError):
        raise AccessError('invalid_metadata') from None
