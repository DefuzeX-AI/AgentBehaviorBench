"""Container entrypoint: validate configuration, listen, then announce readiness."""
import asyncio

from . import events
from .config import ObserverConfig
from .proxy import EgressProxy


async def run() -> None:
    config = ObserverConfig.from_environment()
    server = await EgressProxy(config).serve()
    events.emit("egress_ready", agent_id=config.agent_id, port=config.listen_port,
                allow=[{"host": rule.host, "ports": list(rule.ports)} for rule in config.allow.rules])
    async with server:
        await server.serve_forever()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
