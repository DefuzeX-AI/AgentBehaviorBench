"""Publish immutable payloads once, while retaining ordinary per-step paths."""
import errno
import hashlib
import os
from pathlib import Path
from .legacy_archive import _safe


def publish_payload(temporary, target, step):
    """Use filesystem references within one trajectory; no virtual-file index.

    Unsupported filesystems retain an ordinary file. Publication never mutates
    an existing shared payload.
    """
    temporary, target, step = Path(temporary), Path(target), Path(step)
    if step.parent.name != 'steps':
        temporary.replace(target)
        return
    root = step.parent.parent.resolve()
    if not target.resolve().is_relative_to(root) or target.is_symlink():
        raise ValueError('Payload leaves trajectory')
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
    except OSError as exc:
        if exc.errno not in (errno.EXDEV, errno.EPERM, errno.ENOTSUP, errno.EACCES):
            raise
        temporary.replace(target)
        return
    # The transport path is already complete. Swap its directory entry to the
    # shared inode, then publish atomically over a previous local reference.
    temporary.unlink()
    os.link(blob, temporary)
    temporary.replace(target)
