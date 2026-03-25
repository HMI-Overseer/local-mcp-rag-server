"""
Configuration helpers for the local document RAG project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)


def get_env(name: str, default: str) -> str:
    """Read an environment variable with a default fallback."""
    return os.getenv(name, default)


def resolve_project_path(raw_path: str) -> Path:
    """Resolve a configured path relative to the project root if needed."""
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (PROJECT_ROOT / candidate).resolve()
