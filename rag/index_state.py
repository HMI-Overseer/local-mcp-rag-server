"""
Persistent manifest helpers for incremental indexing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from rag.config import get_env, resolve_project_path


INDEX_STATE_PATH = resolve_project_path(get_env("INDEX_STATE_PATH", "chroma_db/index_state.json"))


def load_index_state() -> Dict[str, Any]:
    """Load the persisted index manifest."""
    if not INDEX_STATE_PATH.exists():
        return {"documents": {}}

    with INDEX_STATE_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict) or "documents" not in data:
        return {"documents": {}}

    documents = data.get("documents")
    if not isinstance(documents, dict):
        return {"documents": {}}

    return {"documents": documents}


def save_index_state(state: Dict[str, Any]) -> None:
    """Persist the index manifest to disk."""
    INDEX_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_STATE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)


def reset_index_state() -> None:
    """Remove the persisted manifest file if present."""
    if INDEX_STATE_PATH.exists():
        INDEX_STATE_PATH.unlink()
