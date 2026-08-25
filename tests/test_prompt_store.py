"""Prompt registry bump / no-op / seed behavior."""

import pytest

from doc_extractor.prompt_store import (
    SEED_SYSTEM_PROMPT,
    SEED_VERSION,
    get_current,
    get_version,
    hash_prompt,
    list_versions,
    save_prompt,
)


def test_missing_registry_seeds_v2(tmp_path):
    path = tmp_path / "registry.json"
    current = get_current(path)
    assert current["version"] == SEED_VERSION
    assert current["system_prompt"] == SEED_SYSTEM_PROMPT
    assert current["hash"] == hash_prompt(SEED_SYSTEM_PROMPT)
    assert path.is_file()


def test_save_unchanged_does_not_bump(tmp_path):
    path = tmp_path / "registry.json"
    get_current(path)
    result = save_prompt(SEED_SYSTEM_PROMPT, path=path)
    assert result["unchanged"] is True
    assert result["version"] == "v2"
    assert get_current(path)["version"] == "v2"
    assert len(list_versions(path)) == 1


def test_save_changed_bumps_and_keeps_history(tmp_path):
    path = tmp_path / "registry.json"
    get_current(path)
    result = save_prompt(SEED_SYSTEM_PROMPT + "Do not guess totals.\n", path=path)
    assert result["unchanged"] is False
    assert result["version"] == "v3"
    current = get_current(path)
    assert current["version"] == "v3"
    assert "Do not guess totals." in current["system_prompt"]
    versions = {item["version"] for item in list_versions(path)}
    assert versions == {"v2", "v3"}
    old = get_version("v2", path=path)
    assert old["system_prompt"] == SEED_SYSTEM_PROMPT
    assert old["is_current"] is False


def test_save_empty_raises(tmp_path):
    path = tmp_path / "registry.json"
    get_current(path)
    with pytest.raises(ValueError, match="empty"):
        save_prompt("   \n", path=path)


def test_trailing_newline_is_not_a_bump(tmp_path):
    path = tmp_path / "registry.json"
    get_current(path)
    result = save_prompt(SEED_SYSTEM_PROMPT.rstrip() + "\n\n", path=path)
    assert result["unchanged"] is True
