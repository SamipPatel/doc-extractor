"""Lab HTTP API (prompt registry, run listing, eval lock)."""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.app import app, eval_job


@pytest.fixture
def client(tmp_path, monkeypatch):
    eval_job.reset()
    out_dir = tmp_path / "eval_runs"
    test_dir = tmp_path / "test_data"
    out_dir.mkdir()
    test_dir.mkdir()
    monkeypatch.setattr("web.app.DEFAULT_OUT_DIR", out_dir)
    monkeypatch.setattr("web.app.DEFAULT_TEST_DIR", test_dir)
    yield TestClient(app)
    eval_job.reset()


def test_get_prompt_seeds_current(client: TestClient) -> None:
    response = client.get("/api/prompt")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "v2"
    assert "You extract structured invoice data" in body["system_prompt"]


def test_save_prompt_bumps_version(client: TestClient) -> None:
    original = client.get("/api/prompt").json()["system_prompt"]
    unchanged = client.post("/api/prompt", json={"system_prompt": original})
    assert unchanged.status_code == 200
    assert unchanged.json()["unchanged"] is True

    bumped = client.post(
        "/api/prompt",
        json={"system_prompt": original + "Prefer printed totals when they match.\n"},
    )
    assert bumped.status_code == 200
    body = bumped.json()
    assert body["unchanged"] is False
    assert body["version"] == "v3"
    assert client.get("/api/prompt").json()["version"] == "v3"
    history = client.get("/api/prompts").json()
    assert {row["version"] for row in history} == {"v2", "v3"}


def test_save_empty_prompt_400(client: TestClient) -> None:
    response = client.post("/api/prompt", json={"system_prompt": "  "})
    assert response.status_code == 400


def test_list_and_compare_runs(client: TestClient, tmp_path: Path) -> None:
    out_dir = tmp_path / "eval_runs"
    a = {
        "timestamp": "2026-08-25T21:00:00+00:00",
        "prompt_version": "v1",
        "prompt_hash": "aaa",
        "model": "claude-sonnet-4-5",
        "total_cost_usd": 0.1,
        "n_docs": 1,
        "n_errors": 0,
        "overall_accuracy": 0.5,
        "overall_counts": [1, 2],
        "per_field_accuracy": {"vendor.name": 0.5},
        "per_field_counts": {"vendor.name": [1, 2]},
        "by_style": {"clean": 0.5},
        "docs": [
            {
                "file": "invoice.pdf",
                "style": "clean",
                "ok": True,
                "error": None,
                "field_results": {"vendor.name": False},
                "accuracy": 0.5,
                "extracted": {"vendor": {"name": "Wrong"}},
                "cost_usd": 0.1,
            }
        ],
    }
    b = {
        **a,
        "timestamp": "2026-08-25T22:00:00+00:00",
        "prompt_version": "v2",
        "prompt_hash": "bbb",
        "overall_accuracy": 1.0,
        "per_field_accuracy": {"vendor.name": 1.0},
        "by_style": {"clean": 1.0},
        "docs": [
            {
                **a["docs"][0],
                "field_results": {"vendor.name": True},
                "accuracy": 1.0,
                "extracted": {"vendor": {"name": "Acme"}},
            }
        ],
    }
    (out_dir / "run_20260825_210000_v1.json").write_text(json.dumps(a), encoding="utf-8")
    (out_dir / "run_20260825_220000_v2.json").write_text(json.dumps(b), encoding="utf-8")
    gold = {
        "file": "invoice.pdf",
        "style": "clean",
        "vendor": {"name": "Acme", "address": "1 Main", "phone": None, "email": None},
    }
    (tmp_path / "test_data" / "ground_truth.json").write_text(
        json.dumps([gold]), encoding="utf-8"
    )

    listed = client.get("/api/runs")
    assert listed.status_code == 200
    ids = [row["id"] for row in listed.json()]
    assert ids == ["run_20260825_220000_v2", "run_20260825_210000_v1"]

    detail = client.get("/api/runs/run_20260825_210000_v1")
    assert detail.status_code == 200
    pairs = detail.json()["docs"][0]["field_pairs"]
    miss = next(row for row in pairs if row["field"] == "vendor.name")
    assert miss["ok"] is False
    assert miss["predicted"] == "Wrong"
    assert miss["gold"] == "Acme"

    compared = client.get(
        "/api/eval/compare",
        params={"a": "run_20260825_210000_v1", "b": "run_20260825_220000_v2"},
    )
    assert compared.status_code == 200
    body = compared.json()
    assert body["overall_delta"] == pytest.approx(0.5)
    assert body["improved"][0]["file"] == "invoice.pdf"


def test_eval_409_when_already_running(client: TestClient, monkeypatch) -> None:
    assert eval_job.try_begin() is True
    response = client.post("/api/eval", json={})
    assert response.status_code == 409


def test_eval_starts_background_job(client: TestClient, monkeypatch) -> None:
    def fake_run_eval(**kwargs):
        progress = kwargs.get("progress")
        if progress:
            progress({"done": 1, "total": 1, "current_file": None, "n_errors": 0})
        return {
            "prompt_version": "v2",
            "overall_accuracy": 1.0,
            "n_docs": 1,
            "n_errors": 0,
            "total_cost_usd": 0.01,
            "artifact": "run_fake_v2.json",
        }

    monkeypatch.setattr("web.app.run_eval", fake_run_eval)
    response = client.post("/api/eval", json={"limit": 3})
    assert response.status_code == 200
    assert response.json()["status"] in {"running", "done"}

    # The worker is a daemon thread; a mocked run may finish before POST returns.
    status = response.json()
    for _ in range(20):
        if status["status"] == "done":
            break
        time.sleep(0.05)
        status = client.get("/api/eval/status").json()
    assert status["status"] == "done"
    assert status["run_id"] == "run_fake_v2"


def test_index_serves_html(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Doc Extractor" in response.text
    assert "Press" not in response.text
