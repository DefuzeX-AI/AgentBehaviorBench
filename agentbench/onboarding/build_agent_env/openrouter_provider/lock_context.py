"""Read bounded lockfile evidence without resolving or installing dependencies."""

from pathlib import Path


def read_lock_excerpt(path: Path, budget: int) -> tuple[str, bool]:
    """Return full text or bounded head/tail excerpts, never a complete-lock claim.

    Head and tail preserve common uv/Pipfile header and Poetry/PDM footer metadata.
    The middle may contain additional constraints; callers must retain truncated.
    Output is UTF-8 text bounded by budget bytes, before the caller's redaction.
    """
    marker = "\n# ... LOCK CONTENT OMITTED; HEAD AND TAIL EXCERPTS ONLY ...\n"
    with path.open("rb") as stream:
        size = stream.seek(0, 2)
        stream.seek(0)
        if size <= budget:
            return stream.read(budget).decode("utf-8-sig"), False
        marker_bytes = len(marker.encode())
        if budget <= marker_bytes:
            return stream.read(budget).decode("utf-8-sig", errors="ignore"), True
        head_bytes = (budget - marker_bytes + 1) // 2
        tail_bytes = budget - marker_bytes - head_bytes
        head = stream.read(head_bytes).decode("utf-8-sig", errors="ignore")
        stream.seek(-tail_bytes, 2)
        tail = stream.read(tail_bytes).decode("utf-8", errors="ignore")
        return head + marker + tail, True
