"""Follow declarative COPY instructions for required bindings, without building."""

import posixpath
import shlex
from pathlib import PurePosixPath

from agentbench.runtime.agentcontainer.config import tomllib
from ..common.errors import BuildError
from .copy_instructions import instructions


def validate_binding_layout(content, session):
    """Require saved bindings beside agent.toml in the final runtime image.

    Track only binding files through local COPY, named/numeric build stages and
    stage inheritance. RUN-created files and variable-expanded paths need an
    explicit COPY instead; this check never executes Docker or upstream code.
    """
    root = session.source.directory
    manifest_text = getattr(session, "completed", {}).get("agent.toml")
    if manifest_text is None:
        manifest_text = (root / "agent.toml").read_text()
    manifest = tomllib.loads(manifest_text)
    reference = manifest.get("adapter", {}).get("binding")
    if not reference:
        return
    selected = "bindings/" + reference.rpartition(":")[0]
    names = set(getattr(session, "plan", {}).get("bindings", [])) | {selected}
    context = {name: name for name in names}
    stages, current, stage_count = {}, None, 0
    for block, copy in instructions(content):
        logical = block.replace("\\\n", " ").strip()
        if not logical or logical.startswith("#"):
            continue
        parts = logical.split(maxsplit=1)
        keyword, value = parts[0], parts[1] if len(parts) == 2 else ""
        if keyword.upper() == "FROM":
            words = [word for word in shlex.split(value) if not word.startswith("--")]
            if not words:
                raise BuildError("Docker FROM instruction needs a base image or stage")
            base = stages.get(words[0])
            current = {"workdir": base["workdir"] if base else "/",
                       "files": dict(base["files"]) if base else {}}
            stages[str(stage_count)] = current
            stage_count += 1
            if len(words) == 3 and words[1].upper() == "AS":
                stages[words[2]] = current
        elif current is not None and keyword.upper() == "WORKDIR":
            current["workdir"] = _absolute(value.strip(), current["workdir"])
        elif current is not None and copy:
            flags, sources, target = copy
            source_stage = next((flag.split("=", 1)[1] for flag in flags if flag.startswith("--from=")), None)
            if source_stage is None:
                files = context
            else:
                files = stages.get(source_stage, {}).get("files", {})
            destination = _absolute(target, current["workdir"])
            for source in sources:
                # Host glob expansion is confined by validate_copy_sources.
                expanded = [path.relative_to(root).as_posix() for path in root.glob(source)] if (
                    source_stage is None and any(char in source for char in "*?[")) else [source]
                for path in expanded:
                    normalized = posixpath.normpath(path)
                    if source_stage is not None:
                        normalized = _absolute(normalized, "/")
                    directory = ((root / path).is_dir() if source_stage is None else
                                 normalized not in files)
                    for location, origin in list(files.items()):
                        relative = _relative(location, normalized, directory)
                        if relative is None:
                            continue
                        into_directory = directory or target.endswith("/") or len(sources) > 1 or len(expanded) > 1
                        dest = posixpath.join(destination, relative) if into_directory else destination
                        current["files"][posixpath.normpath(dest)] = origin
    workdir = manifest.get("launch", {}).get("workdir", "/opt/agent")
    final_files = current["files"] if current else {}
    missing = [name for name in sorted(names) if final_files.get(_absolute(name, workdir)) != name]
    if missing:
        raise BuildError("Dockerfile must COPY required bindings into the final runtime image beside agent.toml "
                         f"under {workdir}: {', '.join(missing)}; use explicit COPY instructions")


def _absolute(path, workdir):
    return posixpath.normpath(posixpath.join(workdir, path))


def _relative(location, source, directory):
    if not directory:
        return posixpath.basename(location) if location == source else None
    try:
        return str(PurePosixPath(location).relative_to(source))
    except ValueError:
        return None
