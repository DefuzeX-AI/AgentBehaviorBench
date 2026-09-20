"""Provider token-count operations: route credentials, preserve actual status/body.

These requests do not generate model output. An unsupported endpoint may return
404 and let the native client use its documented local estimator. Never fabricate
an input-token count or reinterpret this as a failed generation.
"""
from .native import NativeJsonWire
from defuzex_model_interceptor.contracts import SourceSignature


class TokenCountWire(NativeJsonWire):
    auxiliary = True

    def __init__(self, endpoint, auth):
        super().__init__(endpoint)
        self.signature = SourceSignature(('*' + endpoint,), auth)
