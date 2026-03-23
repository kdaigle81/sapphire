"""
Shared Provider Registry Tests

Tests the BaseProviderRegistry pattern used by TTS, STT, Embedding, and LLM.
Covers registration, factory, listing, plugin lifecycle, thread safety,
and cross-system consistency.

Run with: pytest tests/test_provider_registry.py -v
"""
import pytest
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.provider_registry import BaseProviderRegistry


# =============================================================================
# Test Provider Classes
# =============================================================================

class FakeProviderA:
    def __init__(self, **kwargs): self.config = kwargs
    def is_available(self): return True

class FakeProviderB:
    def __init__(self, **kwargs): self.config = kwargs
    def is_available(self): return False

class CrashingProvider:
    def __init__(self, **kwargs): raise RuntimeError("I crash on init")


# =============================================================================
# BaseProviderRegistry Tests
# =============================================================================

class TestBaseProviderRegistry:
    """Test the shared base registry."""

    def _make_registry(self):
        reg = BaseProviderRegistry('test', 'TEST_PROVIDER')
        reg.register_core('provider_a', FakeProviderA, 'Provider A', is_local=True)
        reg.register_core('none', FakeProviderB, 'None')
        return reg

    def test_register_core(self):
        reg = self._make_registry()
        assert 'provider_a' in reg._core
        assert reg._core['provider_a']['display_name'] == 'Provider A'

    def test_register_plugin(self):
        reg = self._make_registry()
        reg.register_plugin('plugin_p', FakeProviderB, 'Plugin P', 'my-plugin')
        assert 'plugin_p' in reg._plugins
        assert reg._plugins['plugin_p']['plugin_name'] == 'my-plugin'

    def test_register_plugin_blocked_by_core(self):
        reg = self._make_registry()
        reg.register_plugin('provider_a', FakeProviderB, 'Conflict', 'bad-plugin')
        # Should NOT overwrite core
        assert reg._core['provider_a']['class'] is FakeProviderA
        assert 'provider_a' not in reg._plugins

    def test_unregister_plugin(self):
        reg = self._make_registry()
        reg.register_plugin('p1', FakeProviderA, 'P1', 'plugin-x')
        reg.register_plugin('p2', FakeProviderB, 'P2', 'plugin-x')
        reg.register_plugin('p3', FakeProviderA, 'P3', 'plugin-y')
        reg.unregister_plugin('plugin-x')
        assert 'p1' not in reg._plugins
        assert 'p2' not in reg._plugins
        assert 'p3' in reg._plugins  # different plugin, untouched

    def test_create_core_provider(self):
        reg = self._make_registry()
        instance = reg.create('provider_a')
        assert isinstance(instance, FakeProviderA)

    def test_create_plugin_provider(self):
        reg = self._make_registry()
        reg.register_plugin('plugin_p', FakeProviderB, 'Plugin P', 'my-plugin')
        instance = reg.create('plugin_p')
        assert isinstance(instance, FakeProviderB)

    def test_create_unknown_falls_back_to_none(self):
        reg = self._make_registry()
        instance = reg.create('nonexistent')
        assert isinstance(instance, FakeProviderB)  # 'none' provider

    def test_create_crash_returns_none(self):
        reg = BaseProviderRegistry('test', 'TEST_PROVIDER')
        reg.register_core('crasher', CrashingProvider, 'Crasher')
        instance = reg.create('crasher')
        assert instance is None

    def test_get_all(self):
        reg = self._make_registry()
        reg.register_plugin('plugin_p', FakeProviderB, 'Plugin P', 'my-plugin', requires_api_key=True)
        all_providers = reg.get_all()
        assert len(all_providers) == 3  # provider_a, none, plugin_p

        keys = [p['key'] for p in all_providers]
        assert 'provider_a' in keys
        assert 'none' in keys
        assert 'plugin_p' in keys

        plugin_entry = next(p for p in all_providers if p['key'] == 'plugin_p')
        assert plugin_entry['is_core'] is False
        assert plugin_entry['requires_api_key'] is True
        assert plugin_entry['plugin_name'] == 'my-plugin'

    def test_get_keys(self):
        reg = self._make_registry()
        reg.register_plugin('pp', FakeProviderA, 'PP', 'plug')
        keys = reg.get_keys()
        assert 'provider_a' in keys
        assert 'none' in keys
        assert 'pp' in keys

    def test_has_key(self):
        reg = self._make_registry()
        assert reg.has_key('provider_a') is True
        assert reg.has_key('none') is True
        assert reg.has_key('nonexistent') is False

    def test_get_entry(self):
        reg = self._make_registry()
        entry = reg.get_entry('provider_a')
        assert entry is not None
        assert entry['class'] is FakeProviderA
        assert reg.get_entry('nonexistent') is None


# =============================================================================
# Thread Safety Tests
# =============================================================================

class TestRegistryThreadSafety:
    """Test concurrent access to the registry."""

    def test_concurrent_register_unregister(self):
        """Multiple threads registering/unregistering shouldn't corrupt the registry."""
        reg = BaseProviderRegistry('test', 'TEST_PROVIDER')
        reg.register_core('none', FakeProviderB, 'None')
        errors = []

        def register_many(start):
            try:
                for i in range(50):
                    reg.register_plugin(f'p{start}_{i}', FakeProviderA, f'P{start}_{i}', f'plugin-{start}')
            except Exception as e:
                errors.append(e)

        def unregister_many(name):
            try:
                for _ in range(50):
                    reg.unregister_plugin(name)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=register_many, args=(1,)),
            threading.Thread(target=register_many, args=(2,)),
            threading.Thread(target=unregister_many, args=('plugin-1',)),
            threading.Thread(target=lambda: [reg.get_all() for _ in range(50)]),
        ]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors, f"Thread errors: {errors}"

    def test_concurrent_create(self):
        """Multiple threads creating providers shouldn't crash."""
        reg = BaseProviderRegistry('test', 'TEST_PROVIDER')
        reg.register_core('a', FakeProviderA, 'A')
        reg.register_core('none', FakeProviderB, 'None')
        results = []
        errors = []

        def create_many():
            try:
                for _ in range(50):
                    r = reg.create('a')
                    results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_many) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors
        assert len(results) == 200
        assert all(isinstance(r, FakeProviderA) for r in results)


# =============================================================================
# TTS Registry Tests
# =============================================================================

class TestTTSRegistry:
    """Test the TTS-specific registry."""

    def test_tts_registry_has_core_providers(self):
        from core.tts.providers import tts_registry
        keys = tts_registry.get_keys()
        assert 'kokoro' in keys
        assert 'none' in keys

    def test_tts_create_kokoro(self):
        from core.tts.providers import tts_registry
        p = tts_registry.create('kokoro')
        assert p is not None
        from core.tts.providers.base import BaseTTSProvider
        assert isinstance(p, BaseTTSProvider)

    def test_tts_create_unknown_fallback(self):
        from core.tts.providers import tts_registry
        p = tts_registry.create('totally_fake')
        assert p is not None
        from core.tts.providers.null import NullTTSProvider
        assert isinstance(p, NullTTSProvider)

    def test_tts_backward_compat(self):
        from core.tts.providers import get_tts_provider
        p = get_tts_provider('kokoro')
        assert p is not None

    def test_tts_plugin_registration(self):
        from core.tts.providers import tts_registry
        tts_registry.register_plugin('test_tts', FakeProviderA, 'Test TTS', 'test-plugin')
        assert tts_registry.has_key('test_tts')
        tts_registry.unregister_plugin('test-plugin')
        assert not tts_registry.has_key('test_tts')


# =============================================================================
# STT Registry Tests
# =============================================================================

class TestSTTRegistry:
    """Test the STT-specific registry."""

    def test_stt_registry_has_core_providers(self):
        from core.stt.providers import stt_registry
        keys = stt_registry.get_keys()
        assert 'faster_whisper' in keys
        assert 'none' in keys

    def test_stt_create_unknown_fallback(self):
        from core.stt.providers import stt_registry
        p = stt_registry.create('nonexistent')
        from core.stt.stt_null import NullWhisperClient
        assert isinstance(p, NullWhisperClient)

    def test_stt_backward_compat(self):
        from core.stt.providers import get_stt_provider
        p = get_stt_provider('none')
        assert p is not None


# =============================================================================
# Embedding Registry Tests
# =============================================================================

class TestEmbeddingRegistry:
    """Test the Embedding-specific registry."""

    def test_embedding_registry_has_core_providers(self):
        from core.embeddings import embedding_registry
        keys = embedding_registry.get_keys()
        assert 'local' in keys
        assert 'none' in keys

    def test_embedding_backward_compat(self):
        from core.embeddings import get_embedder, NullEmbedder
        # get_embedder returns whatever is configured — at minimum it shouldn't crash
        e = get_embedder()
        assert e is not None

    def test_embedding_switch_thread_safe(self):
        """Switching embedding provider should be thread-safe."""
        from core.embeddings import switch_embedding_provider, get_embedder, _embedder_lock
        errors = []

        def switch_back_and_forth():
            try:
                for _ in range(20):
                    switch_embedding_provider('none')
                    switch_embedding_provider('local')
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=switch_back_and_forth) for _ in range(3)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors


# =============================================================================
# LLM Registry Inherits Base
# =============================================================================

class TestLLMRegistryInheritance:
    """Test that LLM ProviderRegistry inherits from BaseProviderRegistry."""

    def test_llm_inherits_base(self):
        from core.chat.llm_providers import provider_registry
        assert isinstance(provider_registry, BaseProviderRegistry)

    def test_llm_has_lock(self):
        from core.chat.llm_providers import provider_registry
        assert hasattr(provider_registry, '_lock')
        assert isinstance(provider_registry._lock, type(threading.Lock()))

    def test_llm_keeps_custom_methods(self):
        from core.chat.llm_providers import provider_registry
        assert hasattr(provider_registry, 'get_presets')
        assert hasattr(provider_registry, 'get_templates')
        assert hasattr(provider_registry, 'get_generation_params')
        assert hasattr(provider_registry, 'get_first_available_provider')


# =============================================================================
# Cross-System Consistency
# =============================================================================

class TestCrossSystemConsistency:
    """All registries should follow the same patterns."""

    def test_all_registries_exist(self):
        from core.tts.providers import tts_registry
        from core.stt.providers import stt_registry
        from core.embeddings import embedding_registry
        from core.chat.llm_providers import provider_registry

        for reg in [tts_registry, stt_registry, embedding_registry, provider_registry]:
            assert isinstance(reg, BaseProviderRegistry)
            assert hasattr(reg, 'system_name')
            assert hasattr(reg, '_lock')

    def test_all_registries_have_none_provider(self):
        """Every system should have a 'none' or null provider for disabled state."""
        from core.tts.providers import tts_registry
        from core.stt.providers import stt_registry
        from core.embeddings import embedding_registry

        assert tts_registry.has_key('none')
        assert stt_registry.has_key('none')
        assert embedding_registry.has_key('none')

    def test_all_registries_create_returns_something(self):
        """Creating with 'none' should always return a provider, never None."""
        from core.tts.providers import tts_registry
        from core.stt.providers import stt_registry
        from core.embeddings import embedding_registry

        assert tts_registry.create('none') is not None
        assert stt_registry.create('none') is not None
        assert embedding_registry.create('none') is not None

    def test_system_names_unique(self):
        from core.tts.providers import tts_registry
        from core.stt.providers import stt_registry
        from core.embeddings import embedding_registry
        from core.chat.llm_providers import provider_registry

        names = [r.system_name for r in [tts_registry, stt_registry, embedding_registry, provider_registry]]
        assert len(names) == len(set(names)), f"Duplicate system names: {names}"


# =============================================================================
# Plugin Loader Integration
# =============================================================================

class TestPluginLoaderProviderSupport:
    """Test that plugin_loader can find registries."""

    def test_get_provider_registry_tts(self):
        from core.plugin_loader import PluginLoader
        loader = PluginLoader()
        reg = loader._get_provider_registry('tts')
        assert reg is not None
        assert reg.system_name == 'tts'

    def test_get_provider_registry_stt(self):
        from core.plugin_loader import PluginLoader
        loader = PluginLoader()
        reg = loader._get_provider_registry('stt')
        assert reg is not None
        assert reg.system_name == 'stt'

    def test_get_provider_registry_embedding(self):
        from core.plugin_loader import PluginLoader
        loader = PluginLoader()
        reg = loader._get_provider_registry('embedding')
        assert reg is not None
        assert reg.system_name == 'embedding'

    def test_get_provider_registry_llm(self):
        from core.plugin_loader import PluginLoader
        loader = PluginLoader()
        reg = loader._get_provider_registry('llm')
        assert reg is not None
        assert reg.system_name == 'llm'

    def test_get_provider_registry_unknown(self):
        from core.plugin_loader import PluginLoader
        loader = PluginLoader()
        assert loader._get_provider_registry('warp_drive') is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
