from scripts.biomedical_milvus_options import install_handler_policy


def handler():
    class Handler:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
    return Handler


def test_policy_applies_to_every_new_connection():
    cls = handler()
    install_handler_policy(cls)
    for address in ("127.0.0.1:1234", "127.0.0.1:5678"):
        instance = cls(address, token="unchanged")
        assert instance.args == (address,)
        assert instance.kwargs["token"] == "unchanged"
        assert instance.kwargs["grpc_options"] == {
            "grpc.keepalive_time_ms": 600000,
            "grpc.keepalive_permit_without_calls": False,
        }


def test_policy_preserves_unrelated_options_and_does_not_mutate_input():
    cls = handler()
    install_handler_policy(cls)
    options = {"grpc.keepalive_time_ms": 10000, "grpc.enable_retries": 0}
    instance = cls(grpc_options=options)
    assert options["grpc.keepalive_time_ms"] == 10000
    assert instance.kwargs["grpc_options"]["grpc.enable_retries"] == 0
    assert instance.kwargs["grpc_options"]["grpc.keepalive_time_ms"] == 600000


def test_policy_is_idempotent_and_keeps_slower_interval():
    cls = handler()
    install_handler_policy(cls)
    initializer = cls.__init__
    install_handler_policy(cls)
    assert cls.__init__ is initializer
    assert cls(grpc_options={"grpc.keepalive_time_ms": 1200000}).kwargs["grpc_options"]["grpc.keepalive_time_ms"] == 1200000
