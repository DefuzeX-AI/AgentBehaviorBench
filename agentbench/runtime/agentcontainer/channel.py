"""Persistent Agent endpoint. Only current requests enter this container."""
import asyncio
import json
from pathlib import Path

from agentbench.observe.store import atomic_json
from agentbench.runtime.agentcontainer.session import AgentSession
from agentbench.runtime.agentcontainer.worker import execute
from agentbench.runtime.agentcontainer.telemetry import WireExporter, WireSpanProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource

REQUESTS = Path('/run/abb-channel/request')
RESPONSES = Path('/run/abb-channel/response')


async def serve(root=Path('/opt/agent'), requests=REQUESTS, responses=RESPONSES):
    session = AgentSession()
    provider = TracerProvider(resource=Resource({'service.name': 'abb-evaluation'}))
    exporter = WireExporter()
    provider.add_span_processor(WireSpanProcessor(exporter))
    sequence = 0
    try:
        while True:
            request = requests / f'{sequence:08d}.json'
            if not request.exists():
                await asyncio.sleep(0.05)
                continue
            envelope = json.loads(request.read_text(encoding='utf-8'))
            folder = responses / f'{sequence:08d}'
            folder.mkdir(exist_ok=True)
            if envelope.get('operation') == 'close':
                await session.aclose()
                atomic_json(folder / 'done.json', {'sequence': sequence, 'session': session.snapshot()})
                return
            exporter.destination = folder / 'spans.jsonl'
            await execute(root, request, folder, provider=provider, session=session,
                          observation_secret_sink=exporter.add_secrets)
            if not provider.force_flush() or exporter.error:
                raise RuntimeError('Agent telemetry transport failed')
            from agentbench.sdk.common.output_permissions import share_output
            share_output(folder)
            atomic_json(folder / 'done.json', {'sequence': sequence, 'session': session.snapshot()})
            sequence += 1
    finally:
        await session.aclose()
        provider.shutdown()


if __name__ == '__main__':
    asyncio.run(serve())
