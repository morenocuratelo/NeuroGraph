"""
Configuration loader for NeuroGraph.

Loads environment variables from `.env` at the project root and exposes
model identifiers, data paths, Neo4j connection settings, and source priors.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Tuple

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _load_env_file(env_file: Path) -> None:
    """
    Load environment variables from a .env file.

    Prefers python-dotenv when available; falls back to a simple parser so
    local development works even without the extra dependency.
    """
    if load_dotenv:
        load_dotenv(env_file)
        return

    if not env_file.exists():
        return

    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(ENV_FILE)

# Ollama models tuned for hybrid (GPU + CPU) inference
VISION_MODEL = os.getenv(
    "VISION_MODEL", "llama3.2-vision:11b"
)  # GPU, fast image/graph analysis
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "nomic-embed-text"
)  # GPU, semantic embeddings
REASONING_MODEL = os.getenv(
    "REASONING_MODEL", "llama3.3:70b-instruct-q4_K_M"
)  # CPU/RAM, deep reasoning & triples
CLASSIFICATION_MODEL = os.getenv(
    "CLASSIFICATION_MODEL", "llama3.1:8b-instruct-fp16"
)  # CPU, quick classification/cleanup

OLLAMA_MODELS = {
    "vision": VISION_MODEL,
    "embedding": EMBEDDING_MODEL,
    "reasoning": REASONING_MODEL,
    "classification": CLASSIFICATION_MODEL,
}

# Data paths and source priors (higher = more trusted)
DATA_ROOT = PROJECT_ROOT / "data"
SOURCE_PRIORS: Dict[str, float] = {
    "01_lab_notes": 1.0,
    "02_textbooks": 0.95,
    "03_papers": 0.85,
}
DATA_PATHS: Dict[str, Path] = {name: DATA_ROOT / name for name in SOURCE_PRIORS}

# Neo4j connection settings
NEO4J_URI: str = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME: str | None = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER")
NEO4J_PASSWORD: str | None = os.getenv("NEO4J_PASSWORD")
NEO4J_AUTH: Tuple[str | None, str | None] = (NEO4J_USERNAME, NEO4J_PASSWORD)


__all__ = [
    "PROJECT_ROOT",
    "ENV_FILE",
    "OLLAMA_BASE_URL",
    "DATA_ROOT",
    "DATA_PATHS",
    "SOURCE_PRIORS",
    "VISION_MODEL",
    "EMBEDDING_MODEL",
    "REASONING_MODEL",
    "CLASSIFICATION_MODEL",
    "OLLAMA_MODELS",
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "NEO4J_AUTH",
]
