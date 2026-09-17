import unittest

from tablegpt.tools import process_content


class TestProcessContent(unittest.TestCase):
    def test_single_string(self):
        content = "Hello"
        expected_output = [{"type": "text", "text": "Hello"}]
        assert process_content(content) == expected_output

    def test_list_of_strings(self):
        content = ["Hello", "World"]
        expected_output = [{"type": "text", "text": "Hello\nWorld"}]
        assert process_content(content) == expected_output

    def test_list_of_mixed_strings_and_dicts(self):
        content = [
            "Hello",
            {"type": "text", "text": "World"},
            {"type": "image", "url": "image.png"},
        ]
        expected_output = [
            {"type": "text", "text": "Hello\nWorld"},
            {"type": "image", "url": "image.png"},
        ]
        assert process_content(content) == expected_output

    def test_list_of_only_dicts(self):
        content = [
            {"type": "image", "url": "image.png"},
            {"type": "video", "url": "video.mp4"},
        ]
        expected_output = [
            {"type": "image", "url": "image.png"},
            {"type": "video", "url": "video.mp4"},
        ]
        assert process_content(content) == expected_output

    def test_empty_string(self):
        content = ""
        expected_output = [{"type": "text", "text": ""}]
        assert process_content(content) == expected_output

    def test_empty_list(self):
        content = []
        expected_output = []
        assert process_content(content) == expected_output

    def test_list_with_empty_string(self):
        content = ["", {"type": "image", "url": "image.png"}]
        expected_output = [
            {"type": "text", "text": ""},
            {"type": "image", "url": "image.png"},
        ]
        assert process_content(content) == expected_output

    def test_text_in_dict(self):
        content = [{"type": "text", "text": "Hello"}]
        expected_output = [{"type": "text", "text": "Hello"}]
        assert process_content(content) == expected_output


if __name__ == "__main__":
    unittest.main()
