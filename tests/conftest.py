"""Isolate the prompt registry so tests never bump the real prompts/registry.json."""

import pytest


@pytest.fixture(autouse=True)
def isolate_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "doc_extractor.prompt_store.DEFAULT_REGISTRY_PATH",
        tmp_path / "prompts" / "registry.json",
    )
