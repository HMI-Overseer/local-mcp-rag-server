"""
Helpers for incremental indexing decisions and manifest persistence data.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def build_index_plan(
    current_records: List[Dict[str, Any]],
    previous_documents: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Split scanned records into unchanged, changed/new, and deleted groups."""
    current_by_path = {record["filepath"]: record for record in current_records}
    deleted_filepaths = sorted(set(previous_documents) - set(current_by_path))

    unchanged_records = []
    changed_records = []

    for filepath, record in current_by_path.items():
        previous = previous_documents.get(filepath)
        if previous and previous.get("content_hash") == record["content_hash"]:
            unchanged_records.append(record)
        else:
            changed_records.append(record)

    return unchanged_records, changed_records, deleted_filepaths


def build_manifest_entry(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build a persisted manifest entry from a scanned document record."""
    return {
        "content_hash": record["content_hash"],
        "chunk_count": len(record["chunks"]),
        "title": record["metadata"].get("title", ""),
        "category": record["metadata"].get("category", "general"),
        "tags": record.get("tags", []),
    }
