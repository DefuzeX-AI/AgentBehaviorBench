"""Read-only validation of the pinned upstream Biomedical_Dataset archive."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

EXPECTED_SIZE = 147776208
EXPECTED_SHA256 = '3495a369ff0109be5374395d5eca48095373ebc933fcc98bb97528e671b9f25c'


def inspect_archive(path, *, expected_size=EXPECTED_SIZE, expected_sha256=EXPECTED_SHA256):
    if path.stat().st_size != expected_size:
        raise ValueError('Archive size does not match the pinned Git LFS object')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise ValueError('Archive SHA256 does not match the pinned Git LFS object')
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        for entry in entries:
            name = PurePosixPath(entry.filename)
            if (name.is_absolute() or '..' in name.parts or '\\' in entry.filename
                    or ':' in entry.filename
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError('Unsafe archive member; nothing was extracted')
        pdfs = [entry for entry in entries if not entry.is_dir()
                and entry.filename.lower().endswith('.pdf')]
        if not pdfs:
            raise ValueError('No PDFs found in the upstream archive')
        return {'sha256_verified': True, 'size_verified': True,
                'pdf_count': len(pdfs),
                'total_uncompressed_bytes': sum(entry.file_size for entry in entries),
                'pdf_sample': [entry.filename for entry in pdfs[:5]],
                'archive': str(path.resolve()), 'extracted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', nargs='?', type=Path,
                        default=Path('cache/biomedical-rag/Biomedical_Dataset.zip'))
    args = parser.parse_args()
    try:
        result = inspect_archive(args.archive)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print('Validation failed:', str(error))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
