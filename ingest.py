"""
CLI script to ingest or re-index Markdown documents into the vector database.
Supports resetting the database and specifying custom document directories.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from time import perf_counter
from typing import Dict, List

from rag.config import get_env, resolve_project_path
from rag.embedder import get_embedder
from rag.indexing import build_index_plan, build_manifest_entry
from rag.index_state import load_index_state, reset_index_state, save_index_state
from rag.ingestor import scan_document_directory
from rag.logging_utils import configure_logging
from rag.vectorstore import get_vectorstore


configure_logging()
logger = logging.getLogger("local-context-rag.ingest")

DEFAULT_DOCUMENTS_DIR = str(resolve_project_path(get_env("DOCUMENTS_DIR", "documents")))


def _prepare_chunks(record: Dict[str, object], embeddings: List[List[float]]) -> List[Dict[str, object]]:
    prepared_chunks = []
    chunks = record["chunks"]
    base_metadata = record["metadata"]
    chunk_metadata_list = record.get("chunk_metadata", [])

    for chunk_index, (text_chunk, embedding) in enumerate(zip(chunks, embeddings)):
        # Use per-chunk metadata if available, otherwise use base metadata
        if chunk_metadata_list and chunk_index < len(chunk_metadata_list):
            metadata = dict(chunk_metadata_list[chunk_index])
        else:
            metadata = dict(base_metadata)
        
        # Always ensure chunk_index is set
        metadata["chunk_index"] = chunk_index
        
        prepared_chunks.append(
            {
                "text": text_chunk,
                "embedding": embedding,
                "metadata": metadata,
            }
        )

    return prepared_chunks


def main() -> int:
    """Main CLI entry point for ingesting Markdown documents."""
    parser = argparse.ArgumentParser(
        description="Ingest Markdown documents into the local RAG knowledge base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ingest.py
  python ingest.py --reset
  python ingest.py --documents-dir /path/to/documents
  python ingest.py --reset --documents-dir /path/to/documents
        """,
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset the database before ingesting.",
    )
    parser.add_argument(
        "--documents-dir",
        type=str,
        default=DEFAULT_DOCUMENTS_DIR,
        help=f"Path to documents directory (default: {DEFAULT_DOCUMENTS_DIR})",
    )
    args = parser.parse_args()

    documents_dir = str(Path(args.documents_dir).expanduser())

    print("=" * 60)
    print("Local RAG - Document Ingestion")
    print("=" * 60)
    print()

    logger.info("Starting ingest for documents directory: %s", documents_dir)

    try:
        embedder = get_embedder()
        vectorstore = get_vectorstore()
        logger.info("Components initialized")
        print("OK: Components initialized")
    except Exception as exc:
        logger.error("Error initializing components: %s", exc)
        print(f"ERROR: Error initializing components: {exc}")
        return 1

    try:
        connection_start = perf_counter()
        embedder.embed("test")
        connection_elapsed_ms = (perf_counter() - connection_start) * 1000
        logger.info("LM Studio connection check passed in %.1f ms", connection_elapsed_ms)
        print("OK: LM Studio is reachable and the embedding model is loaded")
    except ConnectionError as exc:
        logger.error("LM Studio connection failed: %s", exc)
        print(f"ERROR: {exc}")
        print("\nPlease ensure:")
        print("  1. LM Studio is running")
        print("  2. An embedding model is loaded")
        print("  3. The local server is enabled in LM Studio settings")
        return 1
    except Exception as exc:
        logger.error("Error testing embedder: %s", exc)
        print(f"ERROR: Error testing embedder: {exc}")
        return 1

    if args.reset:
        print("\nResetting database...")
        try:
            vectorstore.reset_collection()
            reset_index_state()
            logger.info("Database and index manifest reset")
            print("OK: Database reset complete")
        except Exception as exc:
            logger.error("Error resetting database: %s", exc)
            print(f"ERROR: Error resetting database: {exc}")
            return 1

    print(f"\nScanning documents from: {documents_dir}")
    print("-" * 60)

    try:
        records, summary = scan_document_directory(documents_dir)
    except (FileNotFoundError, NotADirectoryError) as exc:
        logger.error("Invalid documents directory: %s", exc)
        print(f"ERROR: {exc}")
        return 1
    except Exception as exc:
        logger.error("Error scanning document files: %s", exc, exc_info=True)
        print(f"ERROR: Error scanning document files: {exc}")
        return 1

    if not records:
        print("ERROR: No valid document chunks found to ingest")
        print("\nPlease ensure:")
        print("  1. The documents directory exists and contains .md files")
        print("  2. The .md files are not empty")
        return 1

    state = load_index_state()
    previous_documents = state.get("documents", {})
    current_records = {record["filepath"]: record for record in records}
    unchanged_records, changed_records, deleted_filepaths = build_index_plan(records, previous_documents)

    print(f"Found {summary['files_found']} file(s), processed {summary['files_processed']}")
    print(f"Skipped {summary['files_skipped']} file(s)")
    print(f"Prepared {summary['chunks_created']} chunk(s)")
    print(f"Unchanged files: {len(unchanged_records)}")
    print(f"Changed or new files: {len(changed_records)}")
    print(f"Deleted files to remove: {len(deleted_filepaths)}")
    print("\nSyncing index...")

    logger.info(
        "Scan summary: found=%s processed=%s skipped=%s unchanged=%s changed=%s deleted=%s",
        summary["files_found"],
        summary["files_processed"],
        summary["files_skipped"],
        len(unchanged_records),
        len(changed_records),
        len(deleted_filepaths),
    )

    for filepath in deleted_filepaths:
        vectorstore.delete_documents_by_filepath(filepath)
        logger.info("Removed deleted document from index: %s", filepath)

    stored_files = 0
    failed_files = 0
    failed_filepaths = set()

    for index, record in enumerate(sorted(changed_records, key=lambda item: item["filepath"]), start=1):
        filepath = record["filepath"]
        try:
            embed_start = perf_counter()
            embeddings = embedder.embed(record["chunks"])
            embed_elapsed_ms = (perf_counter() - embed_start) * 1000

            prepared_chunks = _prepare_chunks(record, embeddings)
            vectorstore.sync_documents_for_source(filepath, prepared_chunks)

            stored_files += 1
            logger.info(
                "Indexed %s (%s chunk(s), %.1f ms embedding)",
                filepath,
                len(prepared_chunks),
                embed_elapsed_ms,
            )
            print(
                f"  File {index}/{len(changed_records)}: synced {filepath} "
                f"({len(prepared_chunks)} chunk(s))"
            )
        except Exception as exc:
            failed_files += 1
            failed_filepaths.add(filepath)
            logger.error("Failed to sync %s: %s", filepath, exc, exc_info=True)
            print(f"ERROR: Failed to sync {filepath}: {exc}")

    changed_filepaths = {record["filepath"] for record in changed_records}
    rebuilt_state: Dict[str, Dict[str, object]] = {}
    for filepath, record in current_records.items():
        if filepath in changed_filepaths:
            if filepath in failed_filepaths:
                previous = previous_documents.get(filepath)
                if previous is not None:
                    rebuilt_state[filepath] = previous
                continue
            rebuilt_state[filepath] = build_manifest_entry(record)
        else:
            previous = previous_documents.get(filepath)
            if previous is not None:
                rebuilt_state[filepath] = previous
            else:
                rebuilt_state[filepath] = build_manifest_entry(record)

    save_index_state({"documents": rebuilt_state})

    print()
    print("=" * 60)
    print("Ingestion Complete")
    print("=" * 60)
    print(f"Files processed: {summary['files_processed']}/{summary['files_found']}")
    print(f"Files unchanged: {len(unchanged_records)}")
    print(f"Files synced: {stored_files}/{len(changed_records)}")
    print(f"Files deleted from index: {len(deleted_filepaths)}")
    print(f"Files failed: {failed_files}")
    print(f"Total chunks in database: {vectorstore.collection.count()}")

    categories = vectorstore.get_all_categories()
    if categories:
        print("\nCategories found:")
        for category in categories:
            print(f"  - {category['category']}: {category['count']} chunk(s)")

    logger.info(
        "Ingest finished: unchanged=%s synced=%s deleted=%s failed=%s total_chunks=%s",
        len(unchanged_records),
        stored_files,
        len(deleted_filepaths),
        failed_files,
        vectorstore.collection.count(),
    )

    print("\nOK: Your knowledge base is ready.")
    print("  Start the MCP server with: python mcp_server.py")
    print("  Or configure it in LM Studio to use the search_documents tool.")
    print()

    return 0 if failed_files == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
