# core/embeddings.py
# Pluggable embedding provider — local ONNX or remote API (same Nomic model)

import logging
import numpy as np
import config

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = 'nomic-ai/nomic-embed-text-v1.5'
EMBEDDING_ONNX_FILE = 'onnx/model_quantized.onnx'


class LocalEmbedder:
    """Lazy-loaded nomic-embed-text-v1.5 via ONNX runtime."""

    def __init__(self):
        self.session = None
        self.tokenizer = None
        self.input_names = None

    def _load(self):
        if self.session is not None:
            return
        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer
            from huggingface_hub import hf_hub_download

            try:
                self.tokenizer = AutoTokenizer.from_pretrained(
                    EMBEDDING_MODEL, trust_remote_code=True, local_files_only=True)
                model_path = hf_hub_download(
                    EMBEDDING_MODEL, EMBEDDING_ONNX_FILE, local_files_only=True)
            except Exception:
                logger.info(f"Downloading embedding model: {EMBEDDING_MODEL}")
                self.tokenizer = AutoTokenizer.from_pretrained(
                    EMBEDDING_MODEL, trust_remote_code=True)
                model_path = hf_hub_download(EMBEDDING_MODEL, EMBEDDING_ONNX_FILE)

            self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
            self.input_names = [i.name for i in self.session.get_inputs()]
            logger.info(f"Embedding model loaded: {EMBEDDING_MODEL} (quantized ONNX)")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self.session = None

    def embed(self, texts, prefix='search_document'):
        self._load()
        if self.session is None:
            return None
        try:
            prefixed = [f'{prefix}: {t}' for t in texts]
            encoded = self.tokenizer(prefixed, return_tensors='np', padding=True,
                                     truncation=True, max_length=512)
            inputs = {k: v for k, v in encoded.items() if k in self.input_names}
            if 'token_type_ids' not in inputs:
                inputs['token_type_ids'] = np.zeros_like(inputs['input_ids'])

            outputs = self.session.run(None, inputs)
            embeddings = outputs[0]
            mask = encoded['attention_mask']
            masked = embeddings * mask[:, :, np.newaxis]
            pooled = masked.sum(axis=1) / mask.sum(axis=1, keepdims=True)
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            norms[norms == 0] = 1
            return (pooled / norms).astype(np.float32)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return None

    @property
    def available(self):
        self._load()
        return self.session is not None


class RemoteEmbedder:
    """OpenAI-compatible embedding API client (for Nomic via TEI, etc.)."""

    @staticmethod
    def _normalize_url(url):
        """Fix common URL mistakes — invisible UX."""
        from urllib.parse import urlparse, urlunparse
        url = url.strip()
        if not url:
            return ''
        if not url.startswith(('http://', 'https://')):
            url = f'http://{url}'
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        if not path.endswith('/v1/embeddings'):
            if path.endswith('/v1'):
                path += '/embeddings'
            elif not path.endswith('/embeddings'):
                path += '/v1/embeddings'
        return urlunparse((parsed.scheme, parsed.netloc, path, '', '', ''))

    def embed(self, texts, prefix='search_document'):
        raw_url = getattr(config, 'EMBEDDING_API_URL', '')
        url = self._normalize_url(raw_url)
        if not url:
            return None
        try:
            import httpx
            from core.credentials_manager import credentials
            key = credentials.get_service_api_key('embedding') or getattr(config, 'EMBEDDING_API_KEY', '')
            headers = {}
            if key:
                headers['Authorization'] = f'Bearer {key}'

            prefixed = [f'{prefix}: {t}' for t in texts]
            resp = httpx.post(url, json={'input': prefixed, 'model': EMBEDDING_MODEL},
                              headers=headers, timeout=30.0)
            resp.raise_for_status()
            data = resp.json().get('data', [])
            if not data:
                logger.warning("Remote embedding returned empty data")
                return None
            vecs = np.array([d['embedding'] for d in data], dtype=np.float32)
            # L2-normalize (safe regardless of server behavior)
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1
            return (vecs / norms).astype(np.float32)
        except Exception as e:
            logger.error(f"Remote embedding failed: {e}")
            return None

    @property
    def available(self):
        return bool(self._normalize_url(getattr(config, 'EMBEDDING_API_URL', '')))


class SapphireRouterEmbedder:
    """Forwards embedding requests to a Sapphire Router."""

    def _get_url(self):
        import os
        url = os.environ.get('SAPPHIRE_ROUTER_URL') or getattr(config, 'SAPPHIRE_ROUTER_URL', '')
        return url.rstrip('/')

    def _get_tenant_id(self):
        import os
        return os.environ.get('SAPPHIRE_TENANT_ID') or getattr(config, 'SAPPHIRE_ROUTER_TENANT_ID', '')

    def embed(self, texts, prefix='search_document'):
        url = self._get_url()
        if not url:
            return None
        try:
            import httpx
            headers = {'Content-Type': 'application/json'}
            tenant_id = self._get_tenant_id()
            if tenant_id:
                headers['X-Tenant-ID'] = tenant_id
            resp = httpx.post(
                f'{url}/v1/embeddings/embed',
                json={'texts': texts, 'prefix': prefix},
                headers=headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if 'embeddings' in data:
                return np.array(data['embeddings'], dtype=np.float32)
            return None
        except Exception as e:
            import httpx as _hx
            if isinstance(e, _hx.ConnectError):
                logger.error(f"Sapphire Router embeddings: cannot reach router at {url}")
            else:
                logger.error(f"Sapphire Router embedding failed: {e}")
            return None

    @property
    def available(self):
        return bool(self._get_url())


class NullEmbedder:
    """Disabled — consumers fall back to FTS5/LIKE search."""

    def embed(self, texts, prefix='search_document'):
        return None

    @property
    def available(self):
        return False


# ─── Registry ────────────────────────────────────────────────────────────────

from core.provider_registry import BaseProviderRegistry


class EmbeddingRegistry(BaseProviderRegistry):
    """Embedding provider registry — core + plugin providers."""

    def __init__(self):
        super().__init__('embedding', 'EMBEDDING_PROVIDER')
        self.register_core('local', LocalEmbedder, 'Local (Nomic)', is_local=True)
        self.register_core('none', NullEmbedder, 'None (disabled)', is_local=True)

    def create(self, key, **kwargs):
        entry = self._core.get(key) or self._plugins.get(key)
        if not entry:
            if key and key != 'none':
                logger.warning(f"[embedding] Unknown provider '{key}', falling back to null")
            entry = self._core.get('none')
            if not entry:
                return None
        try:
            return entry['class']()
        except Exception as e:
            logger.error(f"[embedding] Failed to create '{key}': {e}")
            return NullEmbedder()


embedding_registry = EmbeddingRegistry()


# ─── Singleton + hot-swap ────────────────────────────────────────────────────

import threading
_embedder = None
_embedder_lock = threading.Lock()


def get_embedder():
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:  # double-check after lock
                key = embedding_registry.get_active_key()
                _embedder = embedding_registry.create(key)
    return _embedder


def switch_embedding_provider(provider_name):
    global _embedder
    with _embedder_lock:
        logger.info(f"Switching embedding provider to: {provider_name}")
        _embedder = embedding_registry.create(provider_name or 'none')
    # Reset backfill flag so new provider can re-embed missing memories
    try:
        import functions.memory as mem
        mem._backfill_done = False
    except Exception:
        pass
