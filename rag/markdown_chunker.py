"""
Markdown-aware chunking module for structured content parsing.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from rag.config import get_env


# Configuration
CHUNK_TARGET_SIZE = max(200, int(get_env("CHUNK_TARGET_SIZE", "1400")))
CHUNK_MIN_SIZE = max(100, min(int(get_env("CHUNK_MIN_SIZE", "350")), CHUNK_TARGET_SIZE))
INCLUDE_PARENT_HEADERS = get_env("CHUNK_INCLUDE_PARENT_HEADERS", "true").lower() == "true"
EXTRACT_WIKILINKS = get_env("CHUNK_EXTRACT_WIKILINKS", "true").lower() == "true"

# Regex patterns
HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
WIKILINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")


class MarkdownSection:
    """Represents a section of a Markdown document with hierarchical context."""
    
    def __init__(
        self,
        level: int,
        title: str,
        content: str,
        start_pos: int,
        parent: MarkdownSection | None = None,
    ):
        self.level = level
        self.title = title
        self.content = content
        self.start_pos = start_pos
        self.parent = parent
        self.children: List[MarkdownSection] = []
    
    def get_path(self) -> str:
        """Get the full hierarchical path to this section."""
        if self.parent is None:
            return self.title
        return f"{self.parent.get_path()} > {self.title}"
    
    def get_context_headers(self) -> Dict[str, str]:
        """Get all parent headers as a dictionary."""
        headers = {}
        current = self
        while current is not None:
            headers[f"section_h{current.level}"] = current.title
            current = current.parent
        return headers
    
    def get_full_content(self) -> str:
        """Get content with parent headers prepended if configured."""
        if not INCLUDE_PARENT_HEADERS or self.parent is None:
            return self.content
        
        # Build header chain
        headers = []
        current = self.parent
        while current is not None:
            headers.insert(0, "#" * current.level + " " + current.title)
            current = current.parent
        
        # Add this section's header
        if self.title:
            headers.append("#" * self.level + " " + self.title)
        
        return "\n\n".join(headers + [self.content])


def extract_wikilinks(text: str) -> List[str]:
    """Extract all wikilinks from text."""
    if not EXTRACT_WIKILINKS:
        return []
    
    links = WIKILINK_PATTERN.findall(text)
    # Remove duplicates while preserving order
    seen = set()
    unique_links = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)
    return unique_links


def parse_markdown_sections(text: str) -> List[MarkdownSection]:
    """Parse Markdown text into a hierarchical list of sections."""
    if not text.strip():
        return []
    
    # Find all headers
    headers = []
    for match in HEADER_PATTERN.finditer(text):
        level = len(match.group(1))
        title = match.group(2).strip()
        start_pos = match.start()
        headers.append((level, title, start_pos))
    
    # If no headers found, treat entire document as one section
    if not headers:
        section = MarkdownSection(
            level=1,
            title="",
            content=text.strip(),
            start_pos=0,
            parent=None,
        )
        return [section]
    
    # Build sections with content
    sections = []
    for i, (level, title, start_pos) in enumerate(headers):
        # Find where this section's content starts (after the header line)
        header_end = text.find("\n", start_pos)
        if header_end == -1:
            header_end = len(text)
        else:
            header_end += 1
        
        # Find where this section's content ends (at next header or end of document)
        if i + 1 < len(headers):
            content_end = headers[i + 1][2]
        else:
            content_end = len(text)
        
        content = text[header_end:content_end].strip()
        
        section = MarkdownSection(
            level=level,
            title=title,
            content=content,
            start_pos=start_pos,
            parent=None,
        )
        sections.append(section)
    
    # Build parent-child relationships
    for i, section in enumerate(sections):
        # Find parent by looking backwards for a section with lower level
        for j in range(i - 1, -1, -1):
            if sections[j].level < section.level:
                section.parent = sections[j]
                sections[j].children.append(section)
                break
    
    return sections


def split_large_content(content: str, max_size: int) -> List[str]:
    """Split content that exceeds max_size on paragraph boundaries."""
    if len(content) <= max_size:
        return [content]
    
    # Try splitting on paragraphs first
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    
    chunks = []
    current_chunk = []
    current_size = 0
    
    for para in paragraphs:
        para_len = len(para)
        
        # If single paragraph is too large, split it
        if para_len > max_size:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_size = 0
            
            # Split on sentences
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for sentence in sentences:
                if current_size + len(sentence) > max_size and current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = [sentence]
                    current_size = len(sentence)
                else:
                    current_chunk.append(sentence)
                    current_size += len(sentence)
            continue
        
        # Check if adding this paragraph would exceed limit
        if current_size + para_len + 2 > max_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_size = para_len
        else:
            current_chunk.append(para)
            current_size += para_len + (2 if current_chunk else 0)
    
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    
    return chunks


def chunk_markdown(
    text: str,
    target_chunk_size: int = CHUNK_TARGET_SIZE,
    min_chunk_size: int = CHUNK_MIN_SIZE,
) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Chunk Markdown text intelligently based on document structure.
    
    Returns list of (chunk_text, metadata_dict) tuples.
    """
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    
    # Parse into sections
    sections = parse_markdown_sections(normalized)
    
    chunks_with_metadata = []
    
    for section in sections:
        content = section.get_full_content() if INCLUDE_PARENT_HEADERS else section.content
        
        # Extract wikilinks from the section
        wikilinks = extract_wikilinks(section.content)
        
        # Build metadata for this section
        section_metadata = section.get_context_headers()
        section_metadata["section_path"] = section.get_path()
        if wikilinks:
            section_metadata["linked_entities"] = wikilinks
        
        # If content fits in one chunk, use it as-is
        if len(content) <= target_chunk_size:
            if content:  # Don't add empty chunks
                chunks_with_metadata.append((content, section_metadata))
        else:
            # Split large sections
            sub_chunks = split_large_content(content, target_chunk_size)
            for i, sub_chunk in enumerate(sub_chunks):
                # Add sub-chunk index to metadata
                sub_metadata = section_metadata.copy()
                if len(sub_chunks) > 1:
                    sub_metadata["sub_chunk_index"] = i
                    sub_metadata["sub_chunk_total"] = len(sub_chunks)
                chunks_with_metadata.append((sub_chunk, sub_metadata))
    
    return chunks_with_metadata


def chunk_markdown_simple(
    text: str,
    target_chunk_size: int = CHUNK_TARGET_SIZE,
    min_chunk_size: int = CHUNK_MIN_SIZE,
) -> List[str]:
    """
    Chunk Markdown text and return only the text chunks (no metadata).
    Compatible with existing code that expects List[str].
    """
    chunks_with_metadata = chunk_markdown(text, target_chunk_size, min_chunk_size)
    return [chunk for chunk, _ in chunks_with_metadata]