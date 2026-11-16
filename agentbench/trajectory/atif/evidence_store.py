"""Portable, lossless value references. Paths are readable; hashes are integrity metadata.

Reference envelopes are outside the original value, so user keys never become
control markers. The threshold changes storage placement only, never content.
"""
from copy import deepcopy
from pathlib import Path, PurePosixPath
import hashlib
import json
import re

FORMAT = "abb.evidence-value.v1"


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, name):
    if not isinstance(name, str) or "\\" in name or ":" in name:
        raise ValueError("Invalid evidence path")
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or any(p in (".", "..") for p in name.split("/")):
        raise ValueError("Evidence path must be relative and contained")
    root = Path(root).resolve()
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symbolic links are not evidence references")
    if not current.resolve().is_relative_to(root):
        raise ValueError("Evidence path escapes bundle")
    return current


class EvidenceStore:
    def __init__(self, root, threshold=1024):
        self.root = Path(root)
        self.threshold = threshold
        self.files = {}
        self._bytes = {}
        self._values = {}
        self._serial = 0
        self._pool_count = 0
        self._pool_digest = hashlib.sha256()
        self._pool_size = 0
        self.reused_bytes = 0
        from agentbench.observe.store import environment_secrets
        self.secrets = [s.encode("utf-8") for s in environment_secrets() if len(s) >= 8]

    def _name(self, suffix):
        self._serial += 1
        return f"runs/files/body-{self._serial:06d}{suffix}"

    def _check_content(self, data):
        if re.search(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----", data) or any(secret in data for secret in self.secrets):
            raise ValueError("Credential material encountered in declared evidence")

    def write(self, data, preferred=None, *, media="application/octet-stream"):
        self._check_content(data)
        key = digest(data)
        # Digest collisions must never silently substitute evidence.
        if key in self._bytes:
            previous = self._bytes[key]
            if safe_path(self.root, previous).read_bytes() != data:
                raise ValueError("Evidence digest collision")
            self.reused_bytes += len(data)
            return previous
        name = preferred or self._name(".bin")
        path = safe_path(self.root, name)
        if path.exists():
            raise ValueError("Evidence filename collision")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.files[name] = {"size": len(data), "sha256": key, "media_type": media}
        self._bytes[key] = name
        return name

    def literal(self, data, preferred=None, *, media="application/octet-stream"):
        return {"path": self.write(data, preferred, media=media), "encoding": "bytes"}

    def text(self, value, preferred=None, *, media="text/plain"):
        ref = {"path": self.write(value.encode("utf-8"), preferred or self._name(".txt"), media=media), "encoding": "utf8"}
        self._values[json_bytes(value)] = ref
        return ref

    def raw_body(self, value, preferred):
        """Register actually captured text; structured values can share these bytes."""
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            parsed = None
            suffix, media = (".sse", "text/event-stream") if value.lstrip().startswith(("data:", "event:", ":")) else (".txt", "text/plain")
        else:
            suffix, media = ".json", "application/json"
        ref = self.text(value, preferred + suffix, media=media)
        if suffix == ".json":
            self._values[json_bytes(parsed)] = {"path": ref["path"], "encoding": "json"}
        return ref

    def pack(self, value):
        refs = []
        def visit(item, pointer, root=False):
            encoded = json_bytes(item)
            if not root and (len(encoded) >= self.threshold or encoded in self._values):
                refs.append({"pointer": pointer, **self.value(item)})
                return None
            if isinstance(item, dict):
                return {k: visit(v, [*pointer, k]) for k, v in item.items()}
            if isinstance(item, list):
                return [visit(v, [*pointer, i]) for i, v in enumerate(item)]
            return item
        result = visit(value, [], root=True)
        return {"format": FORMAT, "value": result, "body_refs": refs}

    def _pool(self, data, encoding):
        # Structured diagnostic values share an append-only readable JSONL file;
        # this avoids thousands of tiny files and filesystem allocation overhead.
        self._check_content(data)
        name = "runs/files/structured-values.jsonl"
        path = safe_path(self.root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = data + b"\n"
        with path.open("ab") as stream:
            stream.write(line)
        self._pool_count += 1
        self._pool_size += len(line)
        self._pool_digest.update(line)
        self.files[name] = {"size": self._pool_size, "sha256": self._pool_digest.hexdigest(), "media_type": "application/x-ndjson"}
        return {"path": name, "encoding": encoding, "line": self._pool_count}

    def value(self, value, preferred=None):
        key = json_bytes(value)
        if key in self._values:
            self.reused_bytes += len(key)
            return dict(self._values[key])
        if isinstance(value, str) and preferred:
            return self.text(value, preferred)
        envelope = self.pack(value)
        if envelope["body_refs"]:
            data, encoding = json_bytes(envelope), "packed"
        else:
            data, encoding = key, "json"
        ref = {"path": self.write(data, preferred, media="application/json"), "encoding": encoding} if preferred else self._pool(data, encoding)
        self._values[key] = ref
        return dict(ref)


class EvidenceResolver:
    def __init__(self, root, files):
        self.root, self.files = Path(root), files
        self.active = set()
        self.cache = {}
        self.lines = {}

    def bytes(self, path):
        if path not in self.files:
            raise ValueError("Unlisted evidence reference")
        data = safe_path(self.root, path).read_bytes()
        info = self.files[path]
        if len(data) != info["size"] or digest(data) != info["sha256"]:
            raise ValueError("Evidence file integrity mismatch: " + path)
        return data

    def resolve(self, ref):
        path, encoding = ref["path"], ref["encoding"]
        key = (path, encoding, ref.get("line"))
        if key in self.active:
            raise ValueError("Cyclic evidence reference")
        if key in self.cache:
            return deepcopy(self.cache[key])
        self.active.add(key)
        try:
            if "line" in ref:
                if path not in self.lines:
                    self.lines[path] = self.bytes(path).splitlines()
                line = ref["line"]
                if type(line) is not int or not 1 <= line <= len(self.lines[path]):
                    raise ValueError("Invalid structured value line")
                data = self.lines[path][line - 1]
            else:
                data = self.bytes(path)
            if encoding == "bytes":
                value = data
            elif encoding == "utf8":
                value = data.decode("utf-8")
            elif encoding == "json":
                value = json.loads(data)
            elif encoding == "packed":
                value = self.unpack(json.loads(data))
            else:
                raise ValueError("Unknown evidence encoding")
            self.cache[key] = value
            return deepcopy(value)
        finally:
            self.active.remove(key)

    def unpack(self, envelope):
        if envelope.get("format") != FORMAT:
            raise ValueError("Unknown evidence envelope")
        value = deepcopy(envelope["value"])
        seen = set()
        for ref in envelope["body_refs"]:
            pointer = ref["pointer"]
            key = tuple(pointer)
            if not pointer or key in seen or any(key[:len(p)] == p or p[:len(key)] == key for p in seen):
                raise ValueError("Overlapping or invalid body reference")
            seen.add(key)
            parent = value
            for part in pointer[:-1]:
                parent = parent[part]
            part = pointer[-1]
            if isinstance(parent, list) and (type(part) is not int or part < 0):
                raise ValueError("Invalid list reference")
            if parent[part] is not None:
                raise ValueError("Body reference must replace an explicit null slot")
            parent[part] = self.resolve(ref)
        return value


def preserve_bytes(store, data, preferred, *, pooled=False):
    """Keep original bytes. JSON rendering is used ONLY after byte equality proof.

The recorded serializer recipe is a reversible encoding, not a claim that a
reformatted payload was the wire body. Noncanonical/binary evidence stays opaque.
"""
    try:
        text = data.decode("utf-8")
        value = json.loads(text)
    except (UnicodeError, ValueError):
        return {"representation": "opaque", "ref": store.literal(data, preferred + ".bin")}
    for indent in (None, 2, 4):
        for ensure_ascii in (False, True):
            for separators in ((",", ":"), (", ", ": "), (",", ": ")):
                options = {"ensure_ascii": ensure_ascii, "separators": separators, "indent": indent}
                rendered = json.dumps(value, **options, allow_nan=False)
                for ending in ("", "\n", "\r\n"):
                    if (rendered + ending).encode("utf-8") == data:
                        return {"representation": "json-render", "ref": store.value(value, None if pooled else preferred + ".json"),
                                "options": options, "ending": ending}
    return {"representation": "opaque", "ref": store.literal(data, preferred + ".bin")}


def restore_bytes(resolver, description):
    value = resolver.resolve(description["ref"])
    if description["representation"] == "opaque":
        if not isinstance(value, bytes):
            raise ValueError("Opaque evidence is not bytes")
        return value
    if description["representation"] != "json-render":
        raise ValueError("Unknown source representation")
    return (json.dumps(value, **description["options"], allow_nan=False) + description["ending"]).encode("utf-8")
