"""
MCP Server for local document RAG.
Uses stdio transport, so stdout is reserved for the MCP protocol.
"""

from __future__ import annotations

import logging
import re
from time import perf_counter
from typing import Any, Dict, List

from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from rag.config import get_env
from rag.embedder import get_embedder
from rag.logging_utils import configure_logging
from rag.search_utils import build_snippet
from rag.vectorstore import get_vectorstore


configure_logging()
logger = logging.getLogger("local-context-rag.server")

SEARCH_MAX_RESULTS = 20
SEARCH_DEFAULT_RESULTS = max(
    1,
    min(int(get_env("SEARCH_DEFAULT_RESULTS", "5")), SEARCH_MAX_RESULTS),
)
SEARCH_SNIPPET_CHARS = max(120, int(get_env("SEARCH_SNIPPET_CHARS", "450")))
SEARCH_MAX_CONTEXT_CHARS = max(300, int(get_env("SEARCH_MAX_CONTEXT_CHARS", "2500")))
READ_DEFAULT_WINDOW_BEFORE = max(0, int(get_env("READ_DEFAULT_WINDOW_BEFORE", "0")))
READ_DEFAULT_WINDOW_AFTER = max(0, int(get_env("READ_DEFAULT_WINDOW_AFTER", "1")))

embedder = get_embedder()
vectorstore = get_vectorstore()
server = Server("local-context-rag")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "untitled"


def _normalize_search_filters(arguments: Dict[str, Any]) -> Dict[str, Any]:
    tags = arguments.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(tag).strip() for tag in tags if str(tag).strip()]

    filters = {
        "category": str(arguments.get("category", "")).strip() or None,
        "source_type": str(arguments.get("source_type", "")).strip() or None,
        "filepath_contains": str(arguments.get("filepath_contains", "")).strip() or None,
        "title_contains": str(arguments.get("title_contains", "")).strip() or None,
        "tags": tags,
    }
    return {key: value for key, value in filters.items() if value}


def _normalize_mode(value: Any) -> str:
    mode = str(value or "vector").strip().lower()
    if mode not in {"vector", "keyword", "hybrid"}:
        return "vector"
    return mode


@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    """List available tools for the MCP client."""
    return [
        Tool(
            name="search_documents",
            description=(
                "Search the local document knowledge base for compact candidate passages. "
                "Use this first, then call get_document_chunk for the most relevant result."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language topic or question to search for",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of candidate results to return",
                        "default": SEARCH_DEFAULT_RESULTS,
                        "maximum": SEARCH_MAX_RESULTS,
                    },
                    "min_score": {
                        "type": "number",
                        "description": "Optional minimum score threshold between 0 and 1",
                    },
                    "max_context_chars": {
                        "type": "integer",
                        "description": "Maximum total snippet characters to return across all results",
                        "default": SEARCH_MAX_CONTEXT_CHARS,
                    },
                    "mode": {
                        "type": "string",
                        "description": "Retrieval mode: vector, keyword, or hybrid",
                        "enum": ["vector", "keyword", "hybrid"],
                        "default": "vector",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional exact category filter",
                    },
                    "source_type": {
                        "type": "string",
                        "description": "Optional exact source type filter such as file or chat",
                    },
                    "filepath_contains": {
                        "type": "string",
                        "description": "Optional case-insensitive filepath substring filter",
                    },
                    "title_contains": {
                        "type": "string",
                        "description": "Optional case-insensitive title substring filter",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tag filters; all listed tags must be present",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_document_chunk",
            description=(
                "Fetch a focused chunk from a document using the doc_id and chunk_id returned by search_documents. "
                "Optionally include neighboring chunks for continuity."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "string",
                        "description": "Document identifier returned by search_documents",
                    },
                    "chunk_id": {
                        "type": "string",
                        "description": "Chunk identifier returned by search_documents",
                    },
                    "window_before": {
                        "type": "integer",
                        "description": "How many chunks before the target to include",
                        "default": READ_DEFAULT_WINDOW_BEFORE,
                    },
                    "window_after": {
                        "type": "integer",
                        "description": "How many chunks after the target to include",
                        "default": READ_DEFAULT_WINDOW_AFTER,
                    },
                },
                "required": ["doc_id", "chunk_id"],
            },
        ),
        Tool(
            name="list_documents",
            description="List indexed documents with optional filters and cursor-based pagination.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of documents to return",
                        "default": 20,
                    },
                    "cursor": {
                        "type": "string",
                        "description": "Pagination cursor returned by a previous list_documents call",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional exact category filter",
                    },
                    "source_type": {
                        "type": "string",
                        "description": "Optional exact source type filter such as file or chat",
                    },
                    "filepath_contains": {
                        "type": "string",
                        "description": "Optional case-insensitive filepath substring filter",
                    },
                    "title_contains": {
                        "type": "string",
                        "description": "Optional case-insensitive title substring filter",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tag filters; all listed tags must be present",
                    },
                },
            },
        ),
        Tool(
            name="list_categories",
            description="List all document categories currently in the knowledge base.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> List[TextContent]:
    """Handle tool execution requests."""
    try:
        if name == "search_documents":
            return await search_documents_tool(arguments)
        if name == "get_document_chunk":
            return await get_document_chunk_tool(arguments)
        if name == "list_documents":
            return await list_documents_tool(arguments)
        if name == "list_categories":
            return await list_categories_tool(arguments)
        return [TextContent(type="text", text=f"Error: Unknown tool '{name}'")]
    except Exception as exc:
        logger.error("Error in tool '%s': %s", name, exc, exc_info=True)
        return [TextContent(type="text", text=f"Error executing {name}: {exc}")]


async def search_documents_tool(arguments: dict) -> List[TextContent]:
    """Search the document knowledge base."""
    try:
        query = str(arguments.get("query", "")).strip()
        n_results = max(
            1,
            min(int(arguments.get("n_results", SEARCH_DEFAULT_RESULTS)), SEARCH_MAX_RESULTS),
        )
        min_score = max(0.0, min(float(arguments.get("min_score", 0.0)), 1.0))
        max_context_chars = max(200, int(arguments.get("max_context_chars", SEARCH_MAX_CONTEXT_CHARS)))
        mode = _normalize_mode(arguments.get("mode"))
        filters = _normalize_search_filters(arguments)

        if not query:
            return [TextContent(type="text", text="Error: query parameter is required")]

        if vectorstore.is_empty():
            return [
                TextContent(
                    type="text",
                    text=(
                        "The knowledge base is empty. Please run `python ingest.py` "
                        "to index your documents first."
                    ),
                )
            ]

        query_start = perf_counter()
        query_embedding = None
        if mode in {"vector", "hybrid"}:
            query_embedding = embedder.embed(query)
        raw_results = vectorstore.search(
            query=query,
            query_embedding=query_embedding,
            mode=mode,
            n_results=n_results,
            filters=filters,
            min_score=min_score,
        )
        elapsed_ms = (perf_counter() - query_start) * 1000

        if not raw_results:
            logger.info(
                "Search returned no results in %.1f ms; mode=%s filters=%s min_score=%.2f",
                elapsed_ms,
                mode,
                filters or {},
                min_score,
            )
            return [TextContent(type="text", text=f"No results found for query: {query}")]

        remaining_budget = max_context_chars
        results = []
        for result in raw_results:
            snippet_budget = min(SEARCH_SNIPPET_CHARS, remaining_budget)
            if snippet_budget < 120:
                break
            snippet = build_snippet(result["text"], query, snippet_budget)
            if not snippet:
                continue
            result = dict(result)
            result["snippet"] = snippet
            results.append(result)
            remaining_budget -= len(snippet)

        logger.info(
            "Search completed in %.1f ms with %s result(s); mode=%s filters=%s min_score=%.2f budget=%s",
            elapsed_ms,
            len(results),
            mode,
            filters or {},
            min_score,
            max_context_chars,
        )

        if not results:
            return [TextContent(type="text", text=f"No results found for query: {query}")]

        output = [f"## Search Results for: {query}", ""]
        output.append(f"**Mode:** {mode}")
        output.append(f"**Returned Results:** {len(results)}")
        output.append(f"**Context Budget:** {max_context_chars} chars")
        if filters:
            output.append(f"**Filters:** `{filters}`")
        output.append("")

        for index, result in enumerate(results, start=1):
            metadata = result["metadata"]
            output.append(f"### Result {index}")
            output.append(f"- doc_id: `{result['doc_id']}`")
            output.append(f"- chunk_id: `{result['chunk_id']}`")
            output.append(f"- title: `{metadata.get('title', metadata['filename'])}`")
            output.append(f"- filepath: `{metadata['filepath']}`")
            output.append(f"- source_type: `{metadata.get('source_type', 'file')}`")
            output.append(f"- category: `{metadata.get('category', 'general')}`")
            output.append(f"- tags: `{metadata.get('tags_text', '')}`")
            output.append(f"- score: `{result['score']:.4f}`")
            output.append(f"- locator: `chunk_index={metadata.get('chunk_index', 0)}`")
            output.append("")
            output.append(result["snippet"])
            output.append("")

        return [TextContent(type="text", text="\n".join(output).strip())]

    except ConnectionError as exc:
        return [TextContent(type="text", text=str(exc))]
    except Exception as exc:
        logger.error("Error in search_documents: %s", exc, exc_info=True)
        return [TextContent(type="text", text=f"Error searching documents: {exc}")]


async def get_document_chunk_tool(arguments: dict) -> List[TextContent]:
    """Fetch a specific chunk window from a document."""
    try:
        doc_id = str(arguments.get("doc_id", "")).strip()
        chunk_id = str(arguments.get("chunk_id", "")).strip()
        window_before = max(0, int(arguments.get("window_before", READ_DEFAULT_WINDOW_BEFORE)))
        window_after = max(0, int(arguments.get("window_after", READ_DEFAULT_WINDOW_AFTER)))

        if not doc_id or not chunk_id:
            return [TextContent(type="text", text="Error: doc_id and chunk_id are required")]

        if not chunk_id.startswith(f"{doc_id}::"):
            return [TextContent(type="text", text="Error: chunk_id does not belong to the provided doc_id")]

        try:
            chunk_index = int(chunk_id.rsplit("::", 1)[1])
        except ValueError:
            return [TextContent(type="text", text="Error: invalid chunk_id format")]

        result = vectorstore.get_chunk_window(
            doc_id=doc_id,
            chunk_index=chunk_index,
            window_before=window_before,
            window_after=window_after,
        )
        if result is None:
            return [TextContent(type="text", text=f"No chunk found for {chunk_id}")]

        metadata = result["metadata"]
        logger.info(
            "Fetched chunk window for %s (%s-%s)",
            doc_id,
            metadata["chunk_start"],
            metadata["chunk_end"],
        )

        output = [
            f"## Document Chunk",
            "",
            f"- doc_id: `{result['doc_id']}`",
            f"- chunk_id: `{result['chunk_id']}`",
            f"- title: `{metadata.get('title', metadata['filename'])}`",
            f"- filepath: `{metadata['filepath']}`",
            f"- category: `{metadata.get('category', 'general')}`",
            f"- source_type: `{metadata.get('source_type', 'file')}`",
            f"- chunk_window: `{metadata['chunk_start']}-{metadata['chunk_end']}`",
            "",
            result["text"],
        ]
        return [TextContent(type="text", text="\n".join(output).strip())]

    except Exception as exc:
        logger.error("Error in get_document_chunk: %s", exc, exc_info=True)
        return [TextContent(type="text", text=f"Error fetching document chunk: {exc}")]


async def list_documents_tool(arguments: dict) -> List[TextContent]:
    """List indexed documents."""
    try:
        limit = max(1, min(int(arguments.get("limit", 20)), 100))
        cursor = str(arguments.get("cursor", "")).strip() or None
        filters = _normalize_search_filters(arguments)

        result = vectorstore.list_documents(filters=filters, limit=limit, cursor=cursor)
        items = result["items"]
        next_cursor = result["next_cursor"]

        logger.info(
            "Listed %s document(s); cursor=%s next_cursor=%s filters=%s",
            len(items),
            cursor,
            next_cursor,
            filters or {},
        )

        output = ["## Documents", ""]
        if filters:
            output.append(f"**Filters:** `{filters}`")
            output.append("")

        if not items:
            output.append("No documents found.")
        else:
            for item in items:
                output.append(f"- doc_id: `{item['doc_id']}`")
                output.append(f"  title: `{item['title']}`")
                output.append(f"  filepath: `{item['filepath']}`")
                output.append(f"  source_type: `{item['source_type']}`")
                output.append(f"  category: `{item['category']}`")
                output.append(f"  tags: `{item['tags']}`")
                output.append(f"  chunk_count: `{item['chunk_count']}`")

        output.append("")
        output.append(f"next_cursor: `{next_cursor or ''}`")
        return [TextContent(type="text", text="\n".join(output).strip())]

    except Exception as exc:
        logger.error("Error in list_documents: %s", exc, exc_info=True)
        return [TextContent(type="text", text=f"Error listing documents: {exc}")]


async def list_categories_tool(arguments: dict) -> List[TextContent]:
    """List all categories in the knowledge base."""
    try:
        if vectorstore.is_empty():
            return [
                TextContent(
                    type="text",
                    text=(
                        "The knowledge base is empty. Please run `python ingest.py` "
                        "to index your documents first."
                    ),
                )
            ]

        categories = vectorstore.get_all_categories()
        if not categories:
            return [TextContent(type="text", text="No categories found in the knowledge base.")]

        total_chunks = sum(item["count"] for item in categories)
        logger.info("Listed %s categories (%s chunks)", len(categories), total_chunks)

        output = ["## Document Categories", "", f"**Total Chunks:** {total_chunks}", ""]
        for category in categories:
            output.append(f"- **{category['category']}**: {category['count']} chunk(s)")

        return [TextContent(type="text", text="\n".join(output))]

    except Exception as exc:
        logger.error("Error in list_categories: %s", exc, exc_info=True)
        return [TextContent(type="text", text=f"Error listing categories: {exc}")]


async def main() -> None:
    """Main entry point for the MCP server."""
    logger.info("Starting local document RAG MCP server")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="local-context-rag",
                server_version="1.3.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
