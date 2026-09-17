import unittest

from langchain_core.documents import Document
from tablegpt.retriever import format_columns


class TestFormatColumns(unittest.TestCase):
    def test_format_empty_column_docs(self):
        formated_columns = format_columns([])
        assert formated_columns == ""

    def test_format_column_docs(self):
        docs = [
            Document(
                page_content="column:Sex",
                metadata={
                    "filename": "foo.csv",
                    "column": "Sex",
                    "dtype": "string",
                    "n_unique": 2,
                    "values": ["male", "female"],
                },
            )
        ]
        formated_columns = format_columns(docs)
        hint = """
Here are some extra column information that might help you understand the dataset:
- foo.csv:
  - {"column": Sex, "dtype": "string", "values": ["male", "female"]}
"""
        assert formated_columns == hint

    def test_format_and_compress_column(self):
        docs = [
            Document(
                page_content="column:Sex",
                metadata={
                    "filename": "foo.csv",
                    "column": "Sex",
                    "dtype": "string",
                    "n_unique": 3,
                    "values": ["male", "female", "unknown"],
                },
            )
        ]
        hint = """
Here are some extra column information that might help you understand the dataset:
- foo.csv:
  - {"column": Sex, "dtype": "string", "values": ["mal...", "fem...", ...]}
"""
        formated_columns = format_columns(docs, dataset_cell_length_threshold=3, max_dataset_cells=2)
        assert formated_columns == hint


if __name__ == "__main__":
    unittest.main()
