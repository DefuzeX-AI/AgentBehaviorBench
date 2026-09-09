"""Instance-scoped observation of native async tool methods, with real calls."""
from functools import wraps
from langchain_core.runnables import RunnableLambda


def observe_async_methods(client, names, *, namespace):
    for name in names:
        original = getattr(client, name)

        def bind(method, label):
            async def call(arguments):
                return await method(*arguments["args"], **arguments["kwargs"])
            runnable = RunnableLambda(call, name=label)

            @wraps(method)
            async def wrapped(*args, **kwargs):
                return await runnable.ainvoke({"args": args, "kwargs": kwargs})
            return wrapped

        setattr(client, name, bind(original, f"{namespace}.{name}"))
