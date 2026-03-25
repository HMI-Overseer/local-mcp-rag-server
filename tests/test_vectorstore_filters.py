import unittest

from rag.vectorstore import VectorStore


class VectorStoreFilterTests(unittest.TestCase):
    def test_matches_filters_accepts_matching_metadata(self):
        metadata = {
            "category": "guides",
            "source_type": "file",
            "filepath": "templates/guide.md",
            "title": "Guide to Metadata",
            "tags_text": "metadata, filters",
        }
        filters = {
            "category": "guides",
            "source_type": "file",
            "filepath_contains": "templates",
            "title_contains": "metadata",
            "tags": ["metadata"],
        }

        self.assertTrue(VectorStore._matches_filters(metadata, filters))

    def test_matches_filters_rejects_missing_tag(self):
        metadata = {
            "category": "guides",
            "source_type": "file",
            "filepath": "templates/guide.md",
            "title": "Guide to Metadata",
            "tags_text": "metadata, filters",
        }
        filters = {"tags": ["metadata", "missing"]}

        self.assertFalse(VectorStore._matches_filters(metadata, filters))


if __name__ == "__main__":
    unittest.main()
