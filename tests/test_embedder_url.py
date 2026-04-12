"""
RemoteEmbedder._normalize_url() tests.

This static method silently fixes common embedding API URL mistakes:
  - Missing http:// prefix
  - Missing /v1/embeddings path
  - Trailing slashes
  - URLs that already end with /v1

If this breaks, embeddings silently fail because the URL goes to the wrong
endpoint and returns 404 — no crash, just missing search results. A silent
data-correctness bug, which makes test coverage essential.

Run with: pytest tests/test_embedder_url.py -v
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.embeddings import RemoteEmbedder


@pytest.mark.parametrize("input_url,expected", [
    # Happy path — already correct
    ("http://localhost:8080/v1/embeddings", "http://localhost:8080/v1/embeddings"),
    ("https://api.example.com/v1/embeddings", "https://api.example.com/v1/embeddings"),
    # Missing scheme
    ("localhost:8080/v1/embeddings", "http://localhost:8080/v1/embeddings"),
    ("192.168.1.100:8080/v1/embeddings", "http://192.168.1.100:8080/v1/embeddings"),
    # Missing path
    ("http://localhost:8080", "http://localhost:8080/v1/embeddings"),
    ("http://localhost:8080/", "http://localhost:8080/v1/embeddings"),
    # Missing /embeddings (has /v1)
    ("http://localhost:8080/v1", "http://localhost:8080/v1/embeddings"),
    ("http://localhost:8080/v1/", "http://localhost:8080/v1/embeddings"),
    # Missing both scheme and path
    ("localhost:8080", "http://localhost:8080/v1/embeddings"),
    # Trailing slashes
    ("http://localhost:8080/v1/embeddings/", "http://localhost:8080/v1/embeddings"),
    # Empty / blank
    ("", ""),
    ("  ", ""),
], ids=[
    "already-correct-http", "already-correct-https",
    "missing-scheme-localhost", "missing-scheme-ip",
    "missing-path", "missing-path-trailing-slash",
    "has-v1-no-embeddings", "has-v1-trailing-slash",
    "bare-host-port",
    "trailing-slash",
    "empty", "whitespace-only",
])
def test_normalize_url(input_url, expected):
    assert RemoteEmbedder._normalize_url(input_url) == expected
