from zipfile import ZipInfo

import pytest

from scripts.ingest_biomedical_one import choose_pdf


def member(name, size):
    entry = ZipInfo(name)
    entry.file_size = size
    return entry


def test_selects_smallest_pdf_not_other_files():
    items = [member("large.pdf", 900), member("small.PDF", 100), member("readme.txt", 1)]
    assert choose_pdf(items).filename == "small.PDF"


def test_selection_is_deterministic_and_skips_directories():
    items = [member("z.pdf", 100), member("folder.pdf/", 0), member("a.pdf", 100)]
    assert choose_pdf(items).filename == "a.pdf"


def test_requires_pdf():
    with pytest.raises(ValueError, match="no PDFs"):
        choose_pdf([member("readme.txt", 1)])
