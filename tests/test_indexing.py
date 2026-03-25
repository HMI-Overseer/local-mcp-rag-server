import unittest

from rag.indexing import build_index_plan, build_manifest_entry


def _record(filepath: str, content_hash: str):
    return {
        "filepath": filepath,
        "content_hash": content_hash,
        "chunks": ["chunk 1", "chunk 2"],
        "metadata": {"title": filepath, "category": "general"},
        "tags": ["tag-a"],
    }


class IndexingTests(unittest.TestCase):
    def test_build_index_plan_detects_changed_unchanged_and_deleted(self):
        records = [
            _record("a.md", "hash-a"),
            _record("b.md", "hash-b-new"),
            _record("c.md", "hash-c"),
        ]
        previous_documents = {
            "a.md": {"content_hash": "hash-a"},
            "b.md": {"content_hash": "hash-b-old"},
            "deleted.md": {"content_hash": "hash-old"},
        }

        unchanged, changed, deleted = build_index_plan(records, previous_documents)

        self.assertEqual([record["filepath"] for record in unchanged], ["a.md"])
        self.assertEqual({record["filepath"] for record in changed}, {"b.md", "c.md"})
        self.assertEqual(deleted, ["deleted.md"])

    def test_build_manifest_entry_keeps_incremental_index_fields(self):
        entry = build_manifest_entry(_record("a.md", "hash-a"))

        self.assertEqual(
            entry,
            {
                "content_hash": "hash-a",
                "chunk_count": 2,
                "title": "a.md",
                "category": "general",
                "tags": ["tag-a"],
            },
        )


if __name__ == "__main__":
    unittest.main()
