"""Package exact public model assets for native, offline-capable startup."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_path(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(x in ('..', '.') for x in path.parts):
        raise ValueError('Model asset path must be relative and contained')
    return path


def install(manifest, cache, destination):
    cache, destination = Path(cache), Path(destination)
    cache.mkdir(parents=True, exist_ok=True)
    for asset in manifest['assets']:
        repo = safe_path(asset['repository'])
        name = safe_path(asset['path'])
        revision = asset['revision']
        if len(repo.parts) != 2 or len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
            raise ValueError('Public model repository/revision is not pinned')
        blob = cache / asset['sha256']
        if not blob.exists() or blob.stat().st_size != asset['bytes'] or digest(blob) != asset['sha256']:
            subprocess.run(['curl', '--fail', '--location', '--connect-timeout', '20',
                            '--max-time', '600', '--retry', '2', '--continue-at', '-',
                            f'https://huggingface.co/{repo}/resolve/{revision}/{name}'
                            f'?download=true&abb_sha256={asset["sha256"]}&abb_fetch={time.time_ns()}',
                            '-o', str(blob)], check=True, timeout=1850)
        if blob.stat().st_size != asset['bytes'] or digest(blob) != asset['sha256']:
            raise ValueError('Pinned public model asset checksum mismatch')
        repo_cache = destination / ('models--' + str(repo).replace('/', '--'))
        target = repo_cache / 'snapshots' / revision / str(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(blob, target)
        (repo_cache / 'refs').mkdir(exist_ok=True)
        (repo_cache / 'refs/main').write_text(revision)
    print('PINNED_PUBLIC_MODEL_ASSETS_VERIFIED=' + str(len(manifest['assets'])), flush=True)


if __name__ == '__main__':
    install(json.loads((ROOT / 'local-models.json').read_text()),
            '/var/cache/abb-octomind-models', '/opt/octomind-model-cache')
