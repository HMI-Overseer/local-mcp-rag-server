import unittest
from unittest import mock
from pathlib import Path

from rag.ingestor import (
    build_document_record,
    chunk_text,
    normalize_tags,
    parse_frontmatter,
)


class IngestorTests(unittest.TestCase):
    def test_parse_frontmatter_extracts_metadata_and_body(self):
        content = """---
title: Example Note
category: research
tags:
  - lore
  - moon
author: user
---
This is the body.
"""
        frontmatter, body = parse_frontmatter(content)

        self.assertEqual(frontmatter["title"], "Example Note")
        self.assertEqual(frontmatter["category"], "research")
        self.assertEqual(frontmatter["author"], "user")
        self.assertEqual(body.strip(), "This is the body.")

    def test_normalize_tags_handles_string_and_list_forms(self):
        self.assertEqual(normalize_tags("a, b\nc"), ["a", "b", "c"])
        self.assertEqual(normalize_tags(["a", "a", "b"]), ["a", "b"])

    def test_chunk_text_splits_large_input_without_empty_chunks(self):
        text = ("Paragraph one. " * 80) + "\n\n" + ("Paragraph two. " * 80)
        chunks = chunk_text(text, target_chunk_size=300, min_chunk_size=100)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.strip() for chunk in chunks))
        self.assertTrue(all(len(chunk) <= 300 for chunk in chunks))

    def test_build_document_record_supports_frontmatter(self):
        with mock.patch("pathlib.Path.read_text") as mock_read_text:
            documents_dir = Path("documents")
            file_path = documents_dir / "note.md"
            mock_read_text.return_value = """---
title: Search Filter Example
category: guides
tags: [metadata, filters]
status: draft
---
Body content for indexing.
"""

            record = build_document_record(file_path, documents_dir)

        self.assertIsNotNone(record)
        self.assertEqual(record["filepath"], "note.md")
        self.assertEqual(record["metadata"]["title"], "Search Filter Example")
        self.assertEqual(record["metadata"]["category"], "guides")
        self.assertEqual(record["metadata"]["tags_text"], "metadata, filters")
        self.assertEqual(record["metadata"]["meta_status"], "draft")
        self.assertEqual(record["chunks"], ["Body content for indexing."])


if __name__ == "__main__":
    unittest.main()
