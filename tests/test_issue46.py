"""Issue #46: introductory documentation links must resolve from each language."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
# CLI.md, Guide.zh-CN.md and Troubleshooting.md were removed with the historical
# documents; the READMEs now carry that material, so they must not link to them.
DOCUMENTS = [ROOT / 'README.md', *sorted(ROOT.glob('docs/otherLanguages/README.*.md')),
             ROOT / 'docs' / 'How To Add Agent.md']
HEADING = re.compile(r'^#{1,6}\s+(.+?)\s*$', re.MULTILINE)


def _links(document):
    content = document.read_text(encoding='utf-8')
    for markdown, html in re.findall(r'\]\(([^)]+)\)|(?:href|src)="([^"]+)"', content):
        target = urlsplit(markdown or html)
        if not (target.scheme or target.netloc):
            yield target


def _anchors(document):
    """GitHub heading ids: lower case, punctuation dropped, spaces become hyphens."""
    content = re.sub(r'```.*?```', '', document.read_text(encoding='utf-8'), flags=re.DOTALL)
    return {re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
            for heading in HEADING.findall(content)}


def test_readme_and_onboarding_local_links_exist():
    missing = []
    for document in DOCUMENTS:
        for target in _links(document):
            if target.path and not (document.parent / unquote(target.path)).exists():
                missing.append(f'{document.relative_to(ROOT)} -> {target.path}')
    assert not missing, '\n'.join(missing)


def test_heading_links_name_existing_headings():
    missing = []
    for document in DOCUMENTS:
        for target in _links(document):
            if not target.fragment:
                continue
            destination = (document.parent / unquote(target.path)) if target.path else document
            if destination.suffix == '.md' and unquote(target.fragment) not in _anchors(destination):
                missing.append(f'{document.relative_to(ROOT)} -> {target.geturl()}')
    assert not missing, '\n'.join(missing)


def test_localized_readmes_lead_to_their_troubleshooting_section():
    for document in DOCUMENTS[1:-1]:
        fragments = [unquote(target.fragment) for target in _links(document)
                     if target.fragment and not target.path]
        assert fragments, document.name
        assert set(fragments) <= _anchors(document), document.name
