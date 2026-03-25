"""
Vector store module using ChromaDB for persistent storage of document embeddings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

import chromadb
from chromadb.config import Settings

from rag.config import get_env, resolve_project_path
from rag.search_utils import keyword_score, vector_distance_to_score


CHROMA_DB_PATH = str(resolve_project_path(get_env("CHROMA_DB_PATH", "chroma_db")))
COLLECTION_NAME = get_env("COLLECTION_NAME", "local_context")


class VectorStore:
    """Manages the ChromaDB vector store for indexed documents."""

    def __init__(self):
        """Initialize ChromaDB client with persistent storage."""
        self.client = chromadb.PersistentClient(
            path=CHROMA_DB_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        self._init_collection()

    def _init_collection(self) -> None:
        """Initialize or get the document collection."""
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Local document context knowledge base"},
        )

    @staticmethod
    def _chunk_id(metadata: Dict[str, Any]) -> str:
        return f"{metadata['filepath']}::{metadata['chunk_index']}"

    @staticmethod
    def _matches_filters(metadata: Dict[str, Any], filters: Dict[str, Any] | None) -> bool:
        if not filters:
            return True

        category = filters.get("category")
        if category and metadata.get("category") != category:
            return False

        source_type = filters.get("source_type")
        if source_type and metadata.get("source_type") != source_type:
            return False

        filepath_contains = filters.get("filepath_contains")
        if filepath_contains and filepath_contains.lower() not in metadata.get("filepath", "").lower():
            return False

        title_contains = filters.get("title_contains")
        if title_contains and title_contains.lower() not in metadata.get("title", "").lower():
            return False

        tags = filters.get("tags") or []
        if tags:
            metadata_tags = {
                tag.strip().lower()
                for tag in str(metadata.get("tags_text", "")).split(",")
                if tag.strip()
            }
            if not {tag.lower() for tag in tags}.issubset(metadata_tags):
                return False

        return True

    def add_documents(self, chunks: List[Dict[str, Any]]) -> None:
        """Upsert document chunks into the vector store."""
        if not chunks:
            return

        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for chunk in chunks:
            metadata = chunk["metadata"]
            ids.append(self._chunk_id(metadata))
            embeddings.append(chunk["embedding"])
            documents.append(chunk["text"])
            metadatas.append(metadata)

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def delete_documents_by_filepath(self, filepath: str) -> None:
        """Delete all chunks for a given logical filepath."""
        self.collection.delete(where={"filepath": filepath})

    def sync_documents_for_source(self, filepath: str, chunks: List[Dict[str, Any]]) -> None:
        """Replace all chunks for a logical source with the provided chunk list."""
        existing = self.collection.get(where={"filepath": filepath}, include=[])
        existing_ids: Set[str] = set(existing["ids"])
        new_ids = {self._chunk_id(chunk["metadata"]) for chunk in chunks}
        stale_ids = sorted(existing_ids - new_ids)

        if stale_ids:
            self.collection.delete(ids=stale_ids)

        self.add_documents(chunks)

    def _vector_candidates(
        self,
        query_embedding: List[float],
        candidate_limit: int,
        filters: Dict[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        raw = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(max(candidate_limit, 1), self.collection.count()),
        )

        candidates = []
        for index in range(len(raw["documents"][0])):
            metadata = raw["metadatas"][0][index]
            if not self._matches_filters(metadata, filters):
                continue
            distance = raw["distances"][0][index]
            candidates.append(
                {
                    "text": raw["documents"][0][index],
                    "metadata": metadata,
                    "distance": distance,
                    "vector_score": vector_distance_to_score(distance),
                    "keyword_score": 0.0,
                    "score": vector_distance_to_score(distance),
                    "chunk_id": self._chunk_id(metadata),
                    "doc_id": metadata["filepath"],
                }
            )

        return candidates

    def _keyword_candidates(
        self,
        query: str,
        candidate_limit: int,
        filters: Dict[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        all_docs = self.collection.get(include=["documents", "metadatas"])

        scored = []
        for document, metadata in zip(all_docs["documents"], all_docs["metadatas"]):
            if not self._matches_filters(metadata, filters):
                continue

            score = keyword_score(document, query)
            if score <= 0:
                continue

            scored.append(
                {
                    "text": document,
                    "metadata": metadata,
                    "distance": None,
                    "vector_score": 0.0,
                    "keyword_score": score,
                    "score": score,
                    "chunk_id": self._chunk_id(metadata),
                    "doc_id": metadata["filepath"],
                }
            )

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:candidate_limit]

    def search(
        self,
        query: str,
        query_embedding: List[float] | None,
        mode: str = "vector",
        n_results: int = 5,
        filters: Dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Search by vector, keyword, or hybrid scoring.
        """
        if self.is_empty():
            return []

        requested = max(1, int(n_results))
        candidate_limit = min(max(requested * 6, requested), self.collection.count())
        mode = mode.lower().strip()
        if mode not in {"vector", "keyword", "hybrid"}:
            mode = "vector"

        candidates_by_id: Dict[str, Dict[str, Any]] = {}

        if mode in {"vector", "hybrid"}:
            if query_embedding is None:
                raise ValueError("query_embedding is required for vector or hybrid search")
            for candidate in self._vector_candidates(query_embedding, candidate_limit, filters):
                candidates_by_id[candidate["chunk_id"]] = candidate

        if mode in {"keyword", "hybrid"}:
            for candidate in self._keyword_candidates(query, candidate_limit, filters):
                existing = candidates_by_id.get(candidate["chunk_id"])
                if existing is None:
                    candidates_by_id[candidate["chunk_id"]] = candidate
                else:
                    existing["keyword_score"] = candidate["keyword_score"]
                    if existing.get("distance") is None:
                        existing["distance"] = candidate.get("distance")

        results = list(candidates_by_id.values())
        for item in results:
            if mode == "vector":
                item["score"] = item["vector_score"]
            elif mode == "keyword":
                item["score"] = item["keyword_score"]
            else:
                item["score"] = (item["vector_score"] * 0.7) + (item["keyword_score"] * 0.3)

        filtered = [item for item in results if item["score"] >= min_score]
        filtered.sort(key=lambda item: item["score"], reverse=True)
        return filtered[:requested]

    def get_chunk_window(
        self,
        doc_id: str,
        chunk_index: int,
        window_before: int = 0,
        window_after: int = 0,
    ) -> Dict[str, Any] | None:
        """
        Fetch a focused chunk window from a document.
        """
        file_data = self.collection.get(
            where={"filepath": doc_id},
            include=["documents", "metadatas"],
        )
        if not file_data["documents"]:
            return None

        chunk_map: Dict[int, Dict[str, Any]] = {}
        for document, metadata in zip(file_data["documents"], file_data["metadatas"]):
            chunk_map[int(metadata["chunk_index"])] = {
                "text": document,
                "metadata": metadata,
            }

        start = max(0, chunk_index - max(0, window_before))
        end = chunk_index + max(0, window_after)
        ordered_indices = [index for index in range(start, end + 1) if index in chunk_map]
        if not ordered_indices:
            return None

        base_metadata = dict(chunk_map[ordered_indices[0]]["metadata"])
        base_metadata["chunk_start"] = ordered_indices[0]
        base_metadata["chunk_end"] = ordered_indices[-1]
        base_metadata["matched_chunk_index"] = chunk_index

        return {
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}::{chunk_index}",
            "text": "\n\n".join(chunk_map[index]["text"] for index in ordered_indices).strip(),
            "metadata": base_metadata,
        }

    def list_documents(
        self,
        filters: Dict[str, Any] | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Dict[str, Any]:
        """
        List unique documents with simple cursor-based pagination.
        """
        if self.is_empty():
            return {"items": [], "next_cursor": None}

        all_docs = self.collection.get(include=["metadatas"])
        documents: Dict[str, Dict[str, Any]] = {}

        for metadata in all_docs["metadatas"]:
            if not self._matches_filters(metadata, filters):
                continue

            doc_id = metadata["filepath"]
            entry = documents.setdefault(
                doc_id,
                {
                    "doc_id": doc_id,
                    "title": metadata.get("title", metadata.get("filename", doc_id)),
                    "filepath": doc_id,
                    "source_type": metadata.get("source_type", "file"),
                    "category": metadata.get("category", "general"),
                    "tags": metadata.get("tags_text", ""),
                    "chunk_count": 0,
                },
            )
            entry["chunk_count"] += 1

        items = sorted(documents.values(), key=lambda item: item["filepath"].lower())
        offset = int(cursor) if cursor else 0
        safe_limit = max(1, min(int(limit), 100))
        page = items[offset : offset + safe_limit]
        next_cursor = str(offset + safe_limit) if offset + safe_limit < len(items) else None

        return {"items": page, "next_cursor": next_cursor}

    def get_all_categories(self) -> List[Dict[str, Any]]:
        """Get all unique categories in the knowledge base with chunk counts."""
        if self.is_empty():
            return []

        all_docs = self.collection.get(include=["metadatas"])

        category_counts: Dict[str, int] = {}
        for metadata in all_docs["metadatas"]:
            category = metadata.get("category", "unknown")
            category_counts[category] = category_counts.get(category, 0) + 1

        categories = [
            {"category": category, "count": count}
            for category, count in category_counts.items()
        ]
        categories.sort(key=lambda item: item["category"])
        return categories

    def reset_collection(self) -> None:
        """Delete and recreate the collection from scratch."""
        try:
            self.client.delete_collection(name=COLLECTION_NAME)
        except Exception:
            pass

        self._init_collection()

    def is_empty(self) -> bool:
        """Check if the collection has any documents."""
        return self.collection.count() == 0


def get_vectorstore() -> VectorStore:
    """Factory function to get a VectorStore instance."""
    return VectorStore()
