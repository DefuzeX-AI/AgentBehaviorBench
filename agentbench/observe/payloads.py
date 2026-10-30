"""Publish immutable payloads once, while retaining ordinary per-step paths."""
import errno
import hashlib
import os
import tempfile
from pathlib import Path
from .artifact_paths import _safe


def publish_payload(temporary, target, step):
    """Use filesystem references within one attempt; no virtual-file index.

    Unsupported filesystems retain an ordinary file. Publication never mutates
    an existing shared payload.
    """
    temporary, target, step = Path(temporary), Path(target), Path(step)
    if step.parent.name != 'steps':
        temporary.replace(target)
        return
    root = step.parent.parent.resolve()
    if not target.resolve().is_relative_to(root) or target.is_symlink():
        raise ValueError('Payload leaves attempt')
    blobs = _safe(root, 'blobs')
    if blobs.is_symlink():
        raise ValueError('Linked payload store')
    blobs.mkdir(exist_ok=True)
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    blob = _safe(root, 'blobs/' + digest)
    if blob.is_symlink():
        raise ValueError('Linked payload')
    try:
        os.link(temporary, blob)
    except FileExistsError:
        if hashlib.sha256(blob.read_bytes()).hexdigest() != digest:
            raise ValueError('Stored payload digest mismatch')
        # Keep the complete incoming file until a replacement link is ready.
        # A shared mount may lose visibility of the blob between operations.
        with tempfile.TemporaryDirectory(prefix='.payload-link-', dir=target.parent) as directory:
            linked = Path(directory) / 'payload'
            try:
                os.link(blob, linked)
            except OSError as exc:
                if exc.errno not in (errno.ENOENT, errno.EXDEV, errno.EPERM, errno.ENOTSUP, errno.EACCES):
                    raise
                temporary.replace(target)
            else:
                linked.replace(target)
                temporary.unlink()
        return
    except OSError as exc:
        if exc.errno not in (errno.EXDEV, errno.EPERM, errno.ENOTSUP, errno.EACCES):
            raise
        temporary.replace(target)
        return
    # A newly created blob already shares this inode. Do not unlink the only
    # transport copy and reopen the blob merely to recreate the same link.
    temporary.replace(target)
