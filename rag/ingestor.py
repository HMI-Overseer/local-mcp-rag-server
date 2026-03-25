"""
Ingestor module for processing Markdown documents into chunks and metadata.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from rag.config import get_env
from rag.markdown_chunker import chunk_markdown


logger = logging.getLogger("local-context-rag.ingestor")

FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
TAG_SPLIT_PATTERN = re.compile(r"[,\n]")
CHUNK_TARGET_SIZE = max(200, int(get_env("CHUNK_TARGET_SIZE", "1400")))
CHUNK_MIN_SIZE = max(100, min(int(get_env("CHUNK_MIN_SIZE", "350")), CHUNK_TARGET_SIZE))
CHUNKING_STRATEGY = get_env("CHUNKING_STRATEGY", "markdown").lower()


def _split_large_block(block: str, max_chunk_size: int) -> List[str]:
    """Split an oversized block on sentence and word boundaries."""
    text = block.strip()
    if not text:
        return []

    if len(text) <= max_chunk_size:
        return [text]

    chunks: List[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chunk_size:
            chunks.append(remaining.strip())
            break

        split_at = remaining.rfind(". ", 0, max_chunk_size)
        if split_at == -1:
            split_at = remaining.rfind("\n", 0, max_chunk_size)
        if split_at == -1:
            split_at = remaining.rfind(" ", 0, max_chunk_size)
        if split_at == -1:
            split_at = max_chunk_size
        else:
            split_at += 1

        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].strip()

    return chunks


def chunk_text(
    text: str,
    target_chunk_size: int = CHUNK_TARGET_SIZE,
    min_chunk_size: int = CHUNK_MIN_SIZE,
) -> List[str]:
    """
    Chunk text on section and paragraph boundaries with clean fallback splitting.
    """
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    blocks = [block.strip() for block in normalized.split("\n\n") if block.strip()]
    chunks: List[str] = []
    current_parts: List[str] = []
    current_size = 0

    def flush_current() -> None:
        nonlocal current_parts, current_size
        if not current_parts:
            return
        chunk = "\n\n".join(current_parts).strip()
        if chunk:
            chunks.append(chunk)
        current_parts = []
        current_size = 0

    for block in blocks:
        if len(block) > target_chunk_size:
            flush_current()
            chunks.extend(_split_large_block(block, target_chunk_size))
            continue

        projected_size = current_size + len(block) + (2 if current_parts else 0)
        if current_parts and projected_size > target_chunk_size:
            if current_size >= min_chunk_size:
                flush_current()
            else:
                current_parts.append(block)
                current_size = projected_size
                flush_current()
                continue

        current_parts.append(block)
        current_size = projected_size

    flush_current()
    return chunks


def get_category_from_path(file_path: Path, documents_dir: Path) -> str:
    """Derive category from the immediate parent folder of a file."""
    try:
        rel_path = file_path.relative_to(documents_dir)
    except ValueError:
        return "general"

    if len(rel_path.parts) == 1:
        return "general"

    return rel_path.parts[-2]


def compute_content_hash(content: str) -> str:
    """Compute a stable hash for file content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Extract optional YAML frontmatter and return metadata plus body text."""
    normalized = content.replace("\r\n", "\n")
    match = FRONTMATTER_PATTERN.match(normalized)
    if not match:
        return {}, normalized

    raw_frontmatter = match.group(1)
    body = normalized[match.end():]

    try:
        parsed = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError as exc:
        logger.warning("Invalid frontmatter encountered; ignoring block: %s", exc)
        return {}, normalized

    if not isinstance(parsed, dict):
        logger.warning("Frontmatter was not a mapping; ignoring block")
        return {}, normalized

    return parsed, body


def normalize_tags(value: Any) -> List[str]:
    """Normalize tags from frontmatter into a predictable list of strings."""
    if value is None:
        return []

    if isinstance(value, str):
        raw_parts = TAG_SPLIT_PATTERN.split(value)
    elif isinstance(value, list):
        raw_parts = [str(item) for item in value]
    else:
        raw_parts = [str(value)]

    tags = []
    seen = set()
    for part in raw_parts:
        tag = part.strip()
        if not tag or tag in seen:
            continue
        tags.append(tag)
        seen.add(tag)
    return tags


def _stringify_frontmatter_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return yaml.safe_dump(value, sort_keys=True).strip()


def build_document_record(md_file: Path, documents_dir: Path) -> Dict[str, Any] | None:
    """Build a parsed document record from a Markdown file."""
    content = md_file.read_text(encoding="utf-8")
    if not content.strip():
        return None

    frontmatter, body = parse_frontmatter(content)
    body = body.strip()
    if not body:
        return None

    relative_path = str(md_file.relative_to(documents_dir).as_posix())
    category = str(frontmatter.get("category") or get_category_from_path(md_file, documents_dir))
    title = str(frontmatter.get("title") or md_file.stem)
    source_type = str(frontmatter.get("source_type") or "file")
    tags = normalize_tags(frontmatter.get("tags"))

    base_metadata = {
        "filename": md_file.name,
        "filepath": relative_path,
        "category": category,
        "title": title,
        "source_type": source_type,
        "tags_text": ", ".join(tags),
    }

    for key, value in frontmatter.items():
        if key in {"title", "category", "source_type", "tags"}:
            continue
        base_metadata[f"meta_{key}"] = _stringify_frontmatter_value(value)

    # Use Markdown-aware chunking if configured
    if CHUNKING_STRATEGY == "markdown":
        chunks_with_metadata = chunk_markdown(body, CHUNK_TARGET_SIZE, CHUNK_MIN_SIZE)
        chunks = []
        chunk_metadata_list = []
        
        for chunk_text, section_metadata in chunks_with_metadata:
            # Merge base metadata with section-specific metadata
            chunk_meta = base_metadata.copy()
            chunk_meta.update(section_metadata)
            chunks.append(chunk_text)
            chunk_metadata_list.append(chunk_meta)
        
        return {
            "filepath": relative_path,
            "content_hash": compute_content_hash(content),
            "metadata": base_metadata,
            "tags": tags,
            "chunks": chunks,
            "chunk_metadata": chunk_metadata_list,  # Per-chunk metadata
        }
    else:
        # Fall back to simple paragraph-based chunking
        chunks = chunk_text(body)
        return {
            "filepath": relative_path,
            "content_hash": compute_content_hash(content),
            "metadata": base_metadata,
            "tags": tags,
            "chunks": chunks,
        }


def scan_document_directory(documents_dir: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Recursively scan all Markdown files in a directory.

    Returns document records and a summary.
    """
    documents_path = Path(documents_dir).expanduser().resolve()

    if not documents_path.exists():
        raise FileNotFoundError(f"Documents directory not found: {documents_dir}")

    if not documents_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {documents_dir}")

    records: List[Dict[str, Any]] = []
    files_processed = 0
    files_skipped = 0

    md_files = sorted(documents_path.rglob("*.md"))

    for md_file in md_files:
        try:
            record = build_document_record(md_file, documents_path)
            if record is None:
                files_skipped += 1
                logger.warning("Skipping empty or metadata-only document: %s", md_file)
                continue

            records.append(record)
            files_processed += 1

        except Exception as exc:
            logger.warning("Error processing %s: %s", md_file, exc)
            files_skipped += 1

    summary = {
        "files_found": len(md_files),
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "chunks_created": sum(len(record["chunks"]) for record in records),
    }

    return records, summary


def ingest_document_directory(documents_dir: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Build chunk dictionaries for all Markdown files in a directory.
    """
    records, summary = scan_document_directory(documents_dir)

    all_chunks: List[Dict[str, Any]] = []
    for record in records:
        for chunk_index, text_chunk in enumerate(record["chunks"]):
            metadata = dict(record["metadata"])
            metadata["chunk_index"] = chunk_index
            all_chunks.append({"text": text_chunk, "metadata": metadata})

    return all_chunks, summary
