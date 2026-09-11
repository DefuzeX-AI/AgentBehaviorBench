"""Instance-scoped observation of native async tool methods, with real calls."""
from functools import wraps
from langchain_core.runnables import RunnableLambda


def observe_async_methods(client, names, *, namespace, inspect_result=None):
    for name in names:
        original = getattr(client, name)

        def bind(method, label):
            async def call(arguments, config):
                result = await method(*arguments["args"], **arguments["kwargs"])
                if inspect_result is not None:
                    from langchain_core.callbacks.manager import adispatch_custom_event
                    outcome = inspect_result(result)
                    if outcome is not None:
                        await adispatch_custom_event("abb.tool_outcome", {"name": label, **outcome}, config=config)
                return result
            runnable = RunnableLambda(call, name=label).with_config(metadata={"abb_span_kind": "tool"})

            @wraps(method)
            async def wrapped(*args, **kwargs):
                return await runnable.ainvoke({"args": args, "kwargs": kwargs})
            return wrapped

        setattr(client, name, bind(original, f"{namespace}.{name}"))
