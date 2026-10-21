"""Explicit one-Case generation with a read-only, hash-checked current Profile.

Run inside the Agent SDK image, mounting the current Profile at --profile,
not the image's cached /opt/agent/requirement.md. No credentials go in argv.
"""
from pathlib import Path
import argparse
import hashlib
import json


def checked_profile(path, expected_sha256):
    path = Path(path)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise ValueError('Mounted Agent Profile SHA256 does not match the requested source')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--profile-sha256', required=True)
    parser.add_argument('--environment', required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    profile = checked_profile(args.profile, args.profile_sha256)
    if not Path('/.dockerenv').is_file():
        raise RuntimeError('Official generation must run inside the SDK Docker container')
    # Import paid-service entry points only after the local provenance gate.
    from kuma import create_run
    from agentbench.sdk.plugin.kuma.generation import generate_collection
    from agentbench.sdk.plugin.kuma.environment import generation_profile
    from agentbench.runtime.contracts.environment import ExecutionEnvironment
    from agentbench.sdk.common.artifacts import Artifacts
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    marker = output/'generation.started'
    with marker.open('x') as handle:
        handle.write('One explicitly requested official Case; no automatic retry.\n')
    environment = ExecutionEnvironment.from_dict(json.loads(Path(args.environment).read_text()))
    files = Artifacts(output)
    files.save('source-profile.json', {'path': str(profile), 'sha256': args.profile_sha256,
                                     'cached_image_profile_used': False})
    with generation_profile(profile, environment, files) as effective:
        generate_collection(create_run, count=1, files=files, repo=Path(args.repo), max_attempts=1,
                            options=dict(repo_path=Path(args.repo), agent_profile_path=effective,
                                         storage_path=output/'sdk-storage', allow_local=False,
                                         track_files=False, upload_diff=False, save_local=True,
                                         max_steps=1, timeout=180, operation_wait_timeout=600, max_retries=0))


if __name__ == '__main__':
    main()
