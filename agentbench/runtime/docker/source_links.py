"""Materialize contained file links only in a private build snapshot."""
import shutil


def materialize_file_links(root, check=lambda: None):
    root = root.resolve()
    pending = []
    for path in root.rglob('*'):
        check()
        if not path.is_symlink():
            continue
        try:
            target = path.resolve(strict=True)
        except (OSError, RuntimeError):
            raise ValueError(f'Broken or cyclic build symlink: {path.relative_to(root)}') from None
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError(f'Build symlinks must target an in-tree regular file: {path.relative_to(root)}')
        pending.append((path, target))
    for path, target in pending:
        check()
        path.unlink()
        shutil.copy2(target, path)
