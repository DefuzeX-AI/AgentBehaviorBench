from __future__ import annotations

from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import fitz

from models.image_schemas import ImageAsset
from tools.doc_parser import DocumentParser


def test_extract_images_from_txt_returns_empty_list() -> None:
    root = Path(".runtime/test_tmp") / f"parser_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        txt_path = root / "sample.txt"
        txt_path.write_text("text only disclosure", encoding="utf-8")
        parser = DocumentParser(image_root_dir=root / "images")
        images = parser.extract_images(txt_path, source_file_id="file-1")
        assert images == []
    finally:
        rmtree(root, ignore_errors=True)


def test_validate_image_batch_enforces_image_count_limit() -> None:
    root = Path(".runtime/test_tmp") / f"parser_{uuid4().hex}"
    image_dir = root / "images"
    try:
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / "img.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

        parser = DocumentParser(image_root_dir=image_dir)
        parser._max_images_per_file = 0  # noqa: SLF001 - explicit white-box test for limit guard.

        sample = ImageAsset(
            image_id="img-1",
            source_file_id="file-1",
            source_path=str(image_path),
            page_index=0,
            mime_type="image/png",
            width=1,
            height=1,
            caption_hint=None,
        )

        try:
            parser._validate_image_batch([sample])  # noqa: SLF001 - explicit white-box test for limit guard.
        except ValueError as exc:
            assert "exceeds limit" in str(exc)
        else:
            raise AssertionError("ValueError expected when image count exceeds configured limit.")
    finally:
        rmtree(root, ignore_errors=True)


def test_parse_pdf_without_text_uses_fallback_marker() -> None:
    root = Path(".runtime/test_tmp") / f"parser_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        pdf_path = root / "scan_like.pdf"
        doc = fitz.open()
        doc.new_page(width=200, height=200)
        doc.save(pdf_path)
        doc.close()

        parser = DocumentParser(image_root_dir=root / "images")
        parsed = parser.parse_file(pdf_path)
        assert parsed.file_type == "pdf"
        assert parsed.page_count == 1
        assert len(parsed.page_image_paths) == 1
        assert parsed.page_image_paths[0].endswith(".png")
        assert parsed.text.startswith("[NO_EXTRACTABLE_TEXT_IN_PDF]")
    finally:
        rmtree(root, ignore_errors=True)


def test_parse_pdf_with_text_extracts_content() -> None:
    root = Path(".runtime/test_tmp") / f"parser_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        pdf_path = root / "textual.pdf"
        doc = fitz.open()
        page = doc.new_page(width=300, height=300)
        page.insert_text((72, 72), "OA textual content available", fontsize=12)
        doc.save(pdf_path)
        doc.close()

        parser = DocumentParser(image_root_dir=root / "images")
        parsed = parser.parse_file(pdf_path)
        assert parsed.file_type == "pdf"
        assert "OA textual content available" in parsed.text
        assert len(parsed.page_image_paths) == 1
        assert parsed.page_image_paths[0].endswith(".png")
    finally:
        rmtree(root, ignore_errors=True)


def test_extract_text_from_pdf_page_rebuilds_from_rawdict_chars() -> None:
    class _FakePage:
        def get_text(self, mode):
            if mode in {"text", "blocks", "words"}:
                return [] if mode != "text" else ""
            if mode == "rawdict":
                return {
                    "blocks": [
                        {
                            "lines": [
                                {
                                    "spans": [
                                        {
                                            "text": "",
                                            "chars": [{"c": "审"}, {"c": "查"}, {"c": "意"}, {"c": "见"}],
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            raise AssertionError(f"Unexpected mode: {mode}")

    extracted = DocumentParser._extract_text_from_pdf_page(_FakePage())  # noqa: SLF001
    assert extracted == "审查意见"


def test_parse_pdf_short_text_triggers_ocr_fallback() -> None:
    root = Path(".runtime/test_tmp") / f"parser_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        pdf_path = root / "short_text.pdf"
        doc = fitz.open()
        page = doc.new_page(width=300, height=300)
        page.insert_text((72, 72), "x", fontsize=12)
        doc.save(pdf_path)
        doc.close()

        class _ParserWithMockLLMOcr(DocumentParser):
            def _run_pdf_llm_ocr_fallback(self, *, page_image_paths):  # type: ignore[override]
                return "LLM OCR recovered long patent notice content"

        parser = _ParserWithMockLLMOcr(image_root_dir=root / "images")
        parsed = parser.parse_file(pdf_path)
        assert parsed.text == "LLM OCR recovered long patent notice content"
        assert len(parsed.page_image_paths) == 1
    finally:
        rmtree(root, ignore_errors=True)


def test_parse_pdf_short_text_triggers_llm_ocr_fallback_when_ocr_empty() -> None:
    root = Path(".runtime/test_tmp") / f"parser_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        pdf_path = root / "short_text_llm.pdf"
        doc = fitz.open()
        page = doc.new_page(width=300, height=300)
        page.insert_text((72, 72), "x", fontsize=12)
        doc.save(pdf_path)
        doc.close()

        class _ParserWithMockLLMOcr(DocumentParser):
            def _run_pdf_llm_ocr_fallback(self, *, page_image_paths):  # type: ignore[override]
                return "LLM OCR recovered patent text"

        parser = _ParserWithMockLLMOcr(image_root_dir=root / "images")
        parsed = parser.parse_file(pdf_path)
        assert parsed.text == "LLM OCR recovered patent text"
    finally:
        rmtree(root, ignore_errors=True)
