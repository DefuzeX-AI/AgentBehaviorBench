import unittest
from pathlib import Path

from langchain_core.messages import BaseMessage
from tablegpt.utils import (
    filter_content,
    path_from_uri,
)


class TestPathFromUri(unittest.TestCase):
    @unittest.skip("Cannot test linux path on windows and vice versa")
    def test_valid_file_uri_unix(self):
        """Test a valid 'file:' URI on a Unix system."""
        uri = "file:///home/user/file.txt"
        expected_path = Path("/home/user/file.txt")
        assert path_from_uri(uri) == expected_path

    @unittest.skip("Cannot test linux path on windows and vice versa")
    def test_valid_file_uri_windows(self):
        """Test a valid 'file:' URI on a Windows system."""
        uri = "file:///C:/Users/user/file.txt"
        expected_path = Path("C:/Users/user/file.txt")
        assert path_from_uri(uri) == expected_path

    @unittest.skip("Cannot test linux path on windows and vice versa")
    def test_valid_file_uri_unc_path(self):
        """Test a valid 'file:' URI with a UNC path."""
        uri = "file://localhost/Server/Share/file.txt"
        expected_path = Path("/Server/Share/file.txt")
        assert path_from_uri(uri) == expected_path

    def test_invalid_file_uri(self):
        """Test an invalid 'file:' URI that does not start with 'file:'."""
        uri = "http://example.com/file.txt"
        with self.assertRaises(ValueError) as cm:  # noqa: PT027
            path_from_uri(uri)
        assert str(cm.exception) == f"URI does not start with 'file:': '{uri}'"

    def test_relative_file_uri(self):
        """Test an invalid 'file:' URI that is not absolute."""
        uri = "file:relative/path/file.txt"
        with self.assertRaises(ValueError) as cm:  # noqa: PT027
            path_from_uri(uri)
        assert str(cm.exception) == f"URI is not absolute: '{uri}'"

    @unittest.skip("Cannot test linux path on windows and vice versa")
    def test_invalid_dos_drive(self):
        """Test an invalid 'file:' URI with incorrect DOS drive."""
        uri = "file://C|/path/to/file.txt"
        expected_path = Path("C:/path/to/file.txt")
        assert path_from_uri(uri) != expected_path

    @unittest.skip("Cannot test linux path on windows and vice versa")
    def test_valid_file_uri_with_encoded_characters(self):
        """Test a valid 'file:' URI with encoded characters."""
        uri = "file:///home/user/file%20name.txt"
        expected_path = Path("/home/user/file name.txt")
        assert path_from_uri(uri) == expected_path


class TestFilterContent(unittest.TestCase):
    def test_filter_content_with_string_content(self):
        message = BaseMessage(content="Hello, World!", type="ai")
        result = filter_content(message)
        assert result.content == "Hello, World!"

    def test_filter_content_with_list_of_strings(self):
        message = BaseMessage(content=["Hello", "World"], type="ai")
        result = filter_content(message)
        assert result.content == ["Hello", "World"]

    def test_filter_content_with_list_of_dicts(self):
        message = BaseMessage(
            content=[
                {"type": "text", "text": "Hello"},
                {"type": "image_url", "image_url": "http://example.com/image.jpg"},
            ],
            type="ai",
        )
        result = filter_content(message)
        assert result.content == [{"type": "text", "text": "Hello"}]

    def test_filter_content_with_custom_keep(self):
        message = BaseMessage(
            content=[
                {"type": "text", "text": "Hello"},
                {"type": "image_url", "image_url": "http://example.com/image.jpg"},
            ],
            type="ai",
        )
        result = filter_content(message, keep=["image_url", "text"])
        assert result.content == [
            {"type": "text", "text": "Hello"},
            {"type": "image_url", "image_url": "http://example.com/image.jpg"},
        ]

    def test_filter_content_with_mixed_content(self):
        message = BaseMessage(
            content=[
                "Hello",
                {"type": "text", "text": "World"},
                {"type": "image_url", "image_url": "http://example.com/image.jpg"},
            ],
            type="ai",
        )
        result = filter_content(message)
        assert result.content == ["Hello", {"type": "text", "text": "World"}]

    def test_filter_content_with_no_text_type(self):
        message = BaseMessage(
            content=[
                {"type": "image_url", "image_url": "http://example.com/image.jpg"},
            ],
            type="ai",
        )
        result = filter_content(message)
        assert result.content == []


if __name__ == "__main__":
    unittest.main()
