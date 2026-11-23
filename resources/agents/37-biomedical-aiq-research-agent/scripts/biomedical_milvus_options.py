"""Process-local Milvus Lite connection policy for the RAG infrastructure probe.

NvidiaRAG and NV-Ingest independently construct MilvusClient/ORM connections,
so setting options on only one client leaves the other connections unchanged.
Inject the supported grpc_options at their shared synchronous handler boundary.
No installed package files, request payloads, authentication or RPCs are altered.
"""
from functools import wraps


def install_handler_policy(handler_class):
    original = handler_class.__init__
    if getattr(original, "_biomedical_keepalive_policy", False):
        return

    @wraps(original)
    def initialize(self, *args, **kwargs):
        options = dict(kwargs.get("grpc_options") or {})
        options["grpc.keepalive_time_ms"] = max(
            600000, options.get("grpc.keepalive_time_ms", 600000))
        options["grpc.keepalive_permit_without_calls"] = False
        kwargs["grpc_options"] = options
        original(self, *args, **kwargs)

    initialize._biomedical_keepalive_policy = True
    handler_class.__init__ = initialize


def configure_milvus_lite_connections():
    from pymilvus.client.grpc_handler import GrpcHandler
    install_handler_policy(GrpcHandler)
