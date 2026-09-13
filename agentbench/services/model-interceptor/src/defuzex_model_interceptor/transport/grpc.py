"""HTTP-equivalent error status mapping for gRPC transports."""

def status_code(http_status):
    return {400: 3, 401: 16, 403: 7, 404: 12, 408: 4, 422: 3, 429: 8,
            499: 1, 502: 13, 503: 14, 504: 4}.get(http_status, 13)
