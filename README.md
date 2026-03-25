# Local Context MCP Server for LM Studio

Local, offline RAG for Markdown knowledge bases. Documents are indexed into ChromaDB, searched through MCP tools, and embedded through LM Studio.

## What This Supports

- Plain Markdown indexing with no special format required
- Optional YAML frontmatter for metadata and filterable search
- **Markdown-aware chunking** that preserves document structure and hierarchy
- **Section metadata** including hierarchical paths and parent headers
- **Wikilink extraction** for cross-referencing entities
- Incremental indexing with delete detection and content hashing
- Compact candidate retrieval followed by focused chunk reads
- Local-only operation through LM Studio and ChromaDB

## Prerequisites

- Python 3.12+ (developed and tested with Python 3.12)
- LM Studio running locally
- An embedding model loaded in LM Studio

Recommended embedding model: `nomic-embed-text-v1.5`

## Configuration

The project reads configuration from `.env` in the project root.

Supported environment variables:

- `DOCUMENTS_DIR`
- `CHROMA_DB_PATH`
- `COLLECTION_NAME`
- `INDEX_STATE_PATH`
- `LM_STUDIO_BASE_URL`
- `EMBEDDING_MODEL`
- `SEARCH_DEFAULT_RESULTS`
- `SEARCH_SNIPPET_CHARS`
- `SEARCH_MAX_CONTEXT_CHARS`
- `CHUNK_TARGET_SIZE`
- `CHUNK_MIN_SIZE`
- `CHUNKING_STRATEGY` (markdown or paragraph)
- `CHUNK_INCLUDE_PARENT_HEADERS` (true/false)
- `CHUNK_EXTRACT_WIKILINKS` (true/false)
- `READ_DEFAULT_WINDOW_BEFORE`
- `READ_DEFAULT_WINDOW_AFTER`
- `LOG_LEVEL`

Relative paths in `.env` are resolved from the project root.

## Ingestion Workflow

Index the configured documents folder:

```bash
python ingest.py
```

Rebuild the index from scratch:

```bash
python ingest.py --reset
```

Use another source folder:

```bash
python ingest.py --documents-dir /path/to/documents
```

Incremental behavior:

- unchanged files are skipped
- changed files are re-embedded and synced
- deleted files are removed from the index

If you change `CHUNK_TARGET_SIZE`, `CHUNK_MIN_SIZE`, or `CHUNKING_STRATEGY`, run `python ingest.py --reset` so the stored chunk boundaries match the new retrieval settings.

## Chunking Strategies

The system supports two chunking strategies controlled by `CHUNKING_STRATEGY` in `.env`:

### Markdown-Aware Chunking (Default: `CHUNKING_STRATEGY=markdown`)

This strategy parses Markdown structure to create intelligent chunks:

**Features:**
- Respects document hierarchy (H1, H2, H3 headers)
- Preserves section context with parent headers
- Extracts and indexes wikilinks (`[[entity]]`) for cross-referencing
- Keeps related content together (lists, subsections)
- Adds section metadata to each chunk

**Benefits:**
- Better retrieval accuracy for structured content
- Hierarchical context preserved in search results
- Self-contained chunks with parent header context
- Entity relationship tracking via wikilinks

**Configuration:**
- `CHUNK_INCLUDE_PARENT_HEADERS=true` - Prepend parent headers to chunks
- `CHUNK_EXTRACT_WIKILINKS=true` - Extract `[[wikilinks]]` as metadata

**Example:** A search for "Talion" in a character file will return the chunk with metadata showing it's from "Relationships > Talion — Origin / Whatever", making context clear without needing to fetch parent sections.

### Paragraph-Based Chunking (`CHUNKING_STRATEGY=paragraph`)

Falls back to simple paragraph-based splitting on double newlines. Useful for documents without clear header structure.

## Optional Metadata

Plain `.md` files work without any metadata.

If you want filterable search, you can add YAML frontmatter:

```md
---
title: Example Title
category: guides
tags:
  - metadata
  - filters
source_type: file
status: draft
---
```

Recognized fields:

- `title`
- `category`
- `tags`
- `source_type`

Other frontmatter fields are preserved as extra metadata with a `meta_` prefix.

Example templates live in `documents/`.

## LM Studio MCP Config

Example Windows config:

```json
{
  "mcpServers": {
    "local-context": {
      "command": "C:/path/to/local-mcp-rag-server/venv/Scripts/python.exe",
      "args": ["C:/path/to/local-mcp-rag-server/mcp_server.py"]
    }
  }
}
```

Example macOS/Linux config:

```json
{
  "mcpServers": {
    "local-context": {
      "command": "/path/to/local-mcp-rag-server/venv/bin/python",
      "args": ["/path/to/local-mcp-rag-server/mcp_server.py"]
    }
  }
}
```

Replace the paths with your actual absolute paths to the project directory.

## Tools Exposed to MCP

- `search_documents`
- `get_document_chunk`
- `list_documents`
- `list_categories`

### search_documents

Returns compact candidates, not full document bodies.

Optional inputs:

- `n_results`
- `min_score`
- `max_context_chars`
- `mode`: `vector`, `keyword`, or `hybrid`
- `category`
- `source_type`
- `filepath_contains`
- `title_contains`
- `tags`

Returned candidates include:

- `doc_id`
- `chunk_id`
- title/path/category/source metadata
- score
- a compact snippet
- locator information via `chunk_index`

### get_document_chunk

Fetch the full text for one chunk, optionally with adjacent chunk windows:

- `doc_id`
- `chunk_id`
- `window_before`
- `window_after`

This is the intended second step after `search_documents`.

### list_documents

List indexed documents with:

- `limit`
- `cursor`
- optional metadata filters

### list_categories

List all document categories currently in the knowledge base with chunk counts.

## Chunk Metadata (Markdown Strategy)

When using Markdown-aware chunking, each chunk includes rich metadata:

**Standard metadata:**
- `filepath`, `filename`, `title`, `category`, `tags_text`
- `chunk_index` - Position in document

**Section metadata:**
- `section_h1`, `section_h2`, `section_h3` - Header hierarchy
- `section_path` - Full hierarchical path (e.g., "Summary > Relationships > Talion")
- `linked_entities` - Array of wikilinks found in the section

**Sub-chunk metadata (for split sections):**
- `sub_chunk_index` - Index within a split section
- `sub_chunk_total` - Total sub-chunks in the section

This metadata is searchable and appears in search results, providing rich context without fetching full documents.

## Retrieval Notes

The current defaults are tuned for balanced context use:

- `SEARCH_DEFAULT_RESULTS=5`
- `SEARCH_SNIPPET_CHARS=450`
- `SEARCH_MAX_CONTEXT_CHARS=2500`
- `CHUNK_TARGET_SIZE=1400`
- `CHUNK_MIN_SIZE=350`

This keeps `search_documents` compact while letting `get_document_chunk` fetch broader context only when needed.

## Logging

Logging is designed to be useful without flooding the console:

- startup/config summaries at `INFO`
- ingest summaries and changed/deleted file activity at `INFO`
- malformed or skipped files at `WARNING`
- failures at `ERROR`
- extra detail is available with `LOG_LEVEL=DEBUG`

## Testing

Run:

```bash
python -m unittest discover tests
```

The tests cover chunking, frontmatter parsing, incremental index planning, and metadata filter matching.

## Troubleshooting

### Cannot connect to LM Studio

- Make sure LM Studio is running
- Make sure the local server is enabled
- Make sure an embedding model is loaded
- Verify `LM_STUDIO_BASE_URL` matches LM Studio

### Search returns no results

- Run `python ingest.py`
- If files changed, run `python ingest.py --reset`

### MCP server fails to start

- Verify the `mcp_server.py` path in LM Studio
- Install dependencies with `pip install -r requirements.txt`
