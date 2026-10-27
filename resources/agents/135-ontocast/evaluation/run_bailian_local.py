"""Run one local Case with the documented Bailian provider and Judge transport."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from bailian_judge_transport import BailianJudgeTransport, MODEL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', type=Path, required=True, help='New, unused results directory')
    parser.add_argument('--confirm-free-only', action='store_true', help='Confirm that free-quota-only protection is enabled for this exact model in Beijing')
    args = parser.parse_args()
    if not args.confirm_free_only:
        parser.error('Check free-quota-only protection in Bailian first, then pass --confirm-free-only. This script cannot inspect billing settings.')
    if not os.environ.get('DASHSCOPE_API_KEY'):
        parser.error('Export DASHSCOPE_API_KEY in this process; never put it in an argument or committed file.')
    here = Path(__file__).resolve().parent
    repo = here.parents[3]
    results = args.results_dir.expanduser().resolve()
    if results.exists():
        parser.error('Results directory already exists; preserve it and choose a new path.')
    results.mkdir(parents=True)
    env = os.environ.copy()
    env.update(ABB_MODEL_PROVIDER='bailian', ABB_MODEL=MODEL, BAILIAN_MODEL=MODEL,
               BAILIAN_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1',
               ABB_MODEL_PROVIDERS_CONFIG=str(here / 'bailian-providers.toml'),
               ABB_MAX_PARALLEL_CASES='1', ABB_MAX_PARALLEL_JUDGES='1',
               ABB_LOCAL_JUDGE_MAX_CHARS='4000000', PYTHONUNBUFFERED='1')
    relay = BailianJudgeTransport(results / 'judge-transport.json')
    env.update(ABB_LOCAL_JUDGE_BASE_URL=relay.start(), ABB_LOCAL_JUDGE_MODEL=MODEL,
               ABB_LOCAL_JUDGE_API_KEY=env['DASHSCOPE_API_KEY'])
    case = here / 'smoke-case.json'
    command = [sys.executable, '-m', 'agentbench', 'evaluate', 'ontocast',
               '--sdk', 'local', '--registry', str(repo / 'resources/registry.toml'),
               '--case-file', str(case), '--cases', '1', '--max-steps', '1',
               '--case-retries', '0', '--timeout', '900', '--no-view', '-y',
               '--results-dir', str(results / 'abb')]
    started = time.monotonic()
    process = None
    guard = None
    try:
        with (results / 'cli.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
            while process.poll() is None:
                count = 0
                for path in (results / 'abb').glob('agents/*/cases/*/trajectory/*/logs/network.jsonl'):
                    for line in path.read_bytes().splitlines():
                        try:
                            count += json.loads(line).get('event') == 'llm_request'
                        except json.JSONDecodeError:
                            pass
                if count >= 20 or time.monotonic() - started > 1050:
                    guard = 'model_request_limit' if count >= 20 else 'elapsed_time_limit'
                    process.send_signal(signal.SIGINT)
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=20)
                    break
                time.sleep(2)
    finally:
        relay.close()
    receipt = {'sdk': 'local', 'model': 'bailian/' + MODEL,
               'exit_code': process.returncode if process else None, 'guard': guard,
               'duration_seconds': round(time.monotonic() - started, 2),
               'case_sha256': hashlib.sha256(case.read_bytes()).hexdigest(),
               'official_kuma_calls': 0}
    (results / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    return process.returncode if process else 1


if __name__ == '__main__':
    raise SystemExit(main())
