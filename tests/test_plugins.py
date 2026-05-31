"""Tests for adapter plugin registration."""

from recall.adapters import BASE_URLS, KEY_ENV, REGISTRY, get_adapter, register
from recall.adapters.base import Adapter, ChatResult


class MyAdapter(Adapter):
    provider = "myprov"
    BASE_URL = "https://example.test/v1"
    KEY_ENV = "MYPROV_API_KEY"
    def chat(self, prompt, system=None, history=None):
        return ChatResult("hi", 1, 1, self.model, self.provider)


def test_register_adds_to_registry_and_metadata():
    try:
        register("myprov", MyAdapter, base_url=MyAdapter.BASE_URL, key_env=MyAdapter.KEY_ENV)
        assert "myprov" in REGISTRY
        assert BASE_URLS["myprov"] == "https://example.test/v1"
        assert KEY_ENV["myprov"] == "MYPROV_API_KEY"
        # get_adapter resolves it and injects the registered base_url
        a = get_adapter("myprov", "m", api_key="x")
        assert isinstance(a, MyAdapter)
        assert a.base_url == "https://example.test/v1"
    finally:
        REGISTRY.pop("myprov", None)
        BASE_URLS.pop("myprov", None)
        KEY_ENV.pop("myprov", None)


def test_register_is_case_insensitive():
    try:
        register("MyProv", MyAdapter)
        assert "myprov" in REGISTRY            # normalized to lowercase
    finally:
        REGISTRY.pop("myprov", None)


def test_load_plugins_is_safe_with_none_installed():
    # Importing the package already ran _load_plugins(); calling again must not raise.
    from recall.adapters import _load_plugins
    _load_plugins()
    # Built-in providers are still present.
    assert "openai" in REGISTRY and len(REGISTRY) >= 20
