"""Run a real local echo Agent with a deterministic SDK, without credentials."""
import argparse
import json
from pathlib import Path
import tempfile
from uuid import uuid4

from agentbench.cli.execution import run_benchmark_session
from agentbench.harness import AgentRegistration, SuiteRunner
from examples import local_sdk


def run_demo(output):
    """Return a saved benchmark execution; no Docker, network or .env is used."""
    with tempfile.TemporaryDirectory(prefix='abb-offline-') as temporary:
        root = Path(temporary)
        source = root/'agent'
        source.mkdir()
        name = 'offline_echo_' + uuid4().hex
        (source/f'{name}.py').write_text(
            'from typing_extensions import TypedDict\nfrom langgraph.graph import StateGraph, START, END\n'
            'class State(TypedDict):\n    prompt: str\n    response: str\n'
            'builder = StateGraph(State)\nbuilder.add_node("echo", lambda state: {"response": state["prompt"]})\n'
            'builder.add_edge(START, "echo")\nbuilder.add_edge("echo", END)\ngraph = builder.compile()\n')
        (source/'langgraph.json').write_text(json.dumps({'graphs': {'agent': f'./{name}.py:graph'}}))
        (root/'agent.toml').write_text('[runtime]\ntype="in_process"\n[adapter]\ntype="langgraph"\n'
            'mode="in_process"\nconfig="langgraph.json"\ngraph_id="agent"\ninput_key="prompt"\noutput_key="response"\n')
        agent = AgentRegistration('offline-echo', root, True, 'ready', 'langgraph', 'local demonstration')
        print('Offline demonstration: deterministic local Judge, no Kuma service or model calls.')
        return run_benchmark_session((agent,), runner=SuiteRunner(sdk=local_sdk), output_path=output,
                                     output_fn=print, viewer_starter=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('results/offline-demo.json'))
    execution = run_demo(parser.parse_args().output)
    if execution.result_log is not None:
        print(f'OFFLINE_RESULT={execution.result_log.path}')
    return execution.exit_code


if __name__ == '__main__':
    raise SystemExit(main())
