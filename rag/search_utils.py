"""
Helpers for retrieval scoring and snippet formatting.
"""

from __future__ import annotations

import re
from typing import List


TOKEN_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase word tokens."""
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def vector_distance_to_score(distance: float) -> float:
    """Convert a vector distance to a bounded similarity-like score."""
    return 1.0 / (1.0 + max(distance, 0.0))


def keyword_score(text: str, query: str) -> float:
    """Compute a simple keyword overlap score in the 0-1 range."""
    query_terms = tokenize(query)
    if not query_terms:
        return 0.0

    text_terms = set(tokenize(text))
    matched = sum(1 for term in query_terms if term in text_terms)
    return matched / len(set(query_terms))


def build_snippet(text: str, query: str, max_chars: int) -> str:
    """Build a compact snippet centered around the first query term hit when possible."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned

    query_terms = tokenize(query)
    lowered = cleaned.lower()
    start = 0

    for term in query_terms:
        index = lowered.find(term)
        if index != -1:
            start = max(0, index - max_chars // 3)
            break

    end = min(len(cleaned), start + max_chars)
    snippet = cleaned[start:end].strip()

    if start > 0:
        snippet = "..." + snippet
    if end < len(cleaned):
        snippet = snippet + "..."

    return snippet
