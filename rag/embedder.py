"""
Embedder module for generating embeddings via LM Studio's local API.
Uses the OpenAI SDK as an HTTP client to the local LM Studio endpoint.
"""

from typing import List, Union

from openai import OpenAI

from rag.config import get_env


LM_STUDIO_BASE_URL = get_env("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
EMBEDDING_MODEL = get_env("EMBEDDING_MODEL", "nomic-embed-text-v1.5")


class Embedder:
    """Handles text embedding via LM Studio's local API."""

    def __init__(self):
        """Initialize the OpenAI client pointed at LM Studio."""
        self.client = OpenAI(
            base_url=LM_STUDIO_BASE_URL,
            api_key="lm-studio",
        )
        self.model = EMBEDDING_MODEL

    def embed(self, texts: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """
        Generate embeddings for one or more text strings.
        """
        is_single = isinstance(texts, str)
        text_list = [texts] if is_single else list(texts)

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text_list,
            )
            embeddings = [item.embedding for item in response.data]
            return embeddings[0] if is_single else embeddings

        except Exception as exc:
            error_msg = str(exc).lower()
            if any(token in error_msg for token in ("connection", "refused", "timeout")):
                raise ConnectionError(
                    f"Cannot connect to LM Studio at {LM_STUDIO_BASE_URL}. "
                    "Make sure LM Studio is running and an embedding model is loaded."
                ) from exc
            raise RuntimeError(f"Error generating embeddings: {exc}") from exc


def get_embedder() -> Embedder:
    """Factory function to get an Embedder instance."""
    return Embedder()
