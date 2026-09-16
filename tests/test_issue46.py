"""Issue #46: introductory documentation links must resolve from each language."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


def test_readme_and_onboarding_local_links_exist():
    root = Path(__file__).resolve().parents[1]
    documents = [root / 'README.md', root / 'AGENTS.md', root / 'web/README.md',
                 *root.glob('docs/otherLanguages/README.*.md'),
                 *[root / 'docs' / name for name in
                   ('Guide.zh-CN.md', 'How To Add Agent.md', 'Troubleshooting.md',
                    'Documentation-Issue-Audit.md')]]
    missing = []
    for document in documents:
        content = document.read_text()
        links = re.findall(r'\]\(([^)]+)\)|(?:href|src)="([^"]+)"', content)
        for markdown, html in links:
            target = urlsplit(markdown or html)
            if target.scheme or target.netloc or not target.path:
                continue
            # Check directory-entry spelling too: macOS can otherwise hide links
            # which will break in a case-sensitive Linux checkout or on GitHub.
            path = document.parent
            valid = True
            for part in Path(unquote(target.path)).parts:
                if part == '..':
                    path = path.parent
                elif part != '.':
                    if not path.is_dir() or part not in {p.name for p in path.iterdir()}:
                        valid = False
                        break
                    path = path / part
            if not valid or not path.exists():
                missing.append(f'{document.relative_to(root)} -> {target.path}')
    assert not missing, '\n'.join(missing)
