"""Install publisher-digest-verified native Linux Agent and Node releases."""
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent


def architecture(machine=None):
    """Reject unsupported CPUs before downloading any architecture-specific asset."""
    machine = machine or platform.machine()
    try:
        return {'x86_64': 'amd64', 'aarch64': 'arm64'}[machine]
    except KeyError:
        raise ValueError('Unsupported Linux architecture: ' + machine) from None


def verified_archive(item, cache):
    """Rehash every cache hit and every resumed public release download."""
    archive = cache / item['url'].rsplit('/', 1)[-1]
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != item['sha256']:
        subprocess.run(['curl', '--fail', '--location', '--connect-timeout', '20',
                        '--max-time', '600', '--retry', '2', '--continue-at', '-',
                        item['url'], '-o', str(archive)], check=True, timeout=1850)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != item['sha256']:
        raise RuntimeError('Public release checksum mismatch: ' + archive.name)
    return archive


def main():
    arch = architecture()
    cache = Path('/var/cache/abb-octomind-releases')
    cache.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / 'distributions.json').read_text())
    for item in manifest['architectures'][arch]:
        archive = verified_archive(item, cache)
        with tarfile.open(archive) as source:
            member = source.getmember(item['binary'])
            if not member.isfile():
                raise RuntimeError('Release binary must be a regular file')
            data = source.extractfile(member).read()
        dest = Path('/usr/local/bin') / item['binary']
        dest.write_bytes(data)
        dest.chmod(0o755)
        subprocess.run([str(dest), '--version'], check=True, timeout=30)
    # Official Node includes npm/npx without distro npm's development tree.
    node = json.loads((ROOT / 'node.json').read_text())['architectures'][arch]
    archive = verified_archive(node, cache)
    subprocess.run(['tar', '-xJf', str(archive), '-C', '/usr/local', '--strip-components=1'],
                   check=True, timeout=60)
    subprocess.run(['node', '--version'], check=True, timeout=30)
    subprocess.run(['npm', '--version'], check=True, timeout=30)


if __name__ == '__main__':
    main()
