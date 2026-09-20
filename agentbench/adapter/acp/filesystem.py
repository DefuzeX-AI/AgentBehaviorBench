"""ACP client file callbacks confined to the declared working directory."""
from pathlib import Path
from acp import RequestError
from acp.schema import ReadTextFileResponse, WriteTextFileResponse


def workspace_path(config, path):
    target = Path(path)
    root = Path(config.cwd).resolve()
    if not target.is_absolute() or not target.resolve().is_relative_to(root):
        raise RequestError.invalid_params({'message': 'File path must be inside the session workspace'})
    return target.resolve()


def read_file(config, path, line=None, limit=None):
    target = workspace_path(config, path)
    if line is not None and (type(line) is not int or line < 1):
        raise RequestError.invalid_params({'message': 'line must be positive'})
    if limit is not None and (type(limit) is not int or limit < 1):
        raise RequestError.invalid_params({'message': 'limit must be positive'})
    with target.open('rb') as stream:
        content = stream.read(config.max_output_bytes + 1)
    if len(content) > config.max_output_bytes:
        raise RequestError.invalid_params({'message': 'File exceeds configured output limit'})
    content = content.decode('utf-8')
    if line is not None or limit is not None:
        start = (line or 1) - 1
        content = ''.join(content.splitlines(keepends=True)[start:None if limit is None else start + limit])
    return ReadTextFileResponse(content=content)


def write_file(config, path, content):
    target = workspace_path(config, path)
    if len(content.encode('utf-8')) > config.max_output_bytes:
        raise RequestError.invalid_params({'message': 'File exceeds configured output limit'})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
    return WriteTextFileResponse()
