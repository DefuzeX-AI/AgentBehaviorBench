"""Issue #46: introductory documentation links must resolve from each language."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


def test_readme_and_onboarding_local_links_exist():
    root = Path(__file__).resolve().parents[1]
    documents = [root / 'README.md', *root.glob('docs/otherLanguages/README.*.md'),
                 *[root / 'docs' / name for name in
                   ('CLI.md', 'Guide.zh-CN.md', 'How To Add Agent.md', 'Troubleshooting.md')]]
    missing = []
    for document in documents:
        content = document.read_text()
        links = re.findall(r'\]\(([^)]+)\)|(?:href|src)="([^"]+)"', content)
        for markdown, html in links:
            target = urlsplit(markdown or html)
            if target.scheme or target.netloc or not target.path:
                continue
            if not (document.parent / unquote(target.path)).exists():
                missing.append(f'{document.relative_to(root)} -> {target.path}')
    assert not missing, '\n'.join(missing)
