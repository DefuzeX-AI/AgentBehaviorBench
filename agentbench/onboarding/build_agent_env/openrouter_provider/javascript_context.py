"""Bounded static local JS/TS references; never execute package scripts or imports."""
import json
import re
from pathlib import PurePosixPath


def references(root, path, content):
    names = []
    if path.name == 'package.json':
        try:
            package = json.loads(content)
        except ValueError:
            return []
        bins = package.get('bin', {})
        values = ([bins] if isinstance(bins, str) else list(bins.values()) if isinstance(bins, dict) else [])
        values += [package.get('main', '')]
        scripts = package.get('scripts', {})
        for command in scripts.values() if isinstance(scripts, dict) else []:
            if isinstance(command, str):
                values += re.findall(r'(?:node|tsx|ts-node)\s+([\w./-]+\.(?:[mc]?js|tsx?))', command)
        names = [name for name in values if isinstance(name, str)]
    elif path.suffix in ('.ts', '.tsx', '.js', '.mjs', '.cjs'):
        names = re.findall(r'''(?:from\s*|import\s*\(?|require\s*\()\s*['"](\.[^'"]+)['"]''', content)
    result = []
    for name in names:
        candidate = path.parent / name
        variants = [candidate]
        if candidate.suffix in ('.js', '.mjs'):
            variants += [candidate.with_suffix('.ts')]
        if not candidate.suffix:
            variants += [candidate.with_suffix(ext) for ext in ('.ts', '.tsx', '.js')]
            variants += [candidate / 'index.ts', candidate / 'index.js']
        # Compiled package entrypoints are often absent in source checkouts.
        relative = PurePosixPath(name)
        if relative.parts and relative.parts[0] == 'dist':
            variants += [path.parent / 'src' / PurePosixPath(*relative.parts[1:]).with_suffix('.ts')]
        for target in variants:
            target = target.absolute()
            try:
                local = target.relative_to(root)
            except ValueError:
                continue
            if '..' not in local.parts and target.is_file() and not target.is_symlink():
                result.append(local.as_posix())
    return list(dict.fromkeys(result))
