"""Eval lab HTTP API and static UI."""

import json
import re
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from doc_extractor import prompt_store
from evals.compare import compare_runs, lookup_field
from evals.runner import DEFAULT_OUT_DIR, DEFAULT_TEST_DIR, run_eval
from web.jobs import EvalJob

STATIC_DIR = Path(__file__).resolve().parent / "static"
_RUN_ID_RE = re.compile(r"^run_[A-Za-z0-9_.-]+$")
_META_KEYS = (
    "file",
    "style",
    "layout",
)

eval_job = EvalJob()
app = FastAPI(title="Doc Extractor Lab")


class PromptSave(BaseModel):
    system_prompt: str


class EvalStart(BaseModel):
    limit: int | None = Field(default=None, ge=1)


def _run_file(run_id: str, out_dir: Path) -> Path:
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    # Resolve then is_relative_to so ../../ cannot escape eval_runs/.
    root = out_dir.resolve()
    path = (out_dir / f"{run_id}.json").resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Run not found")
    return path


def _load_run(run_id: str, out_dir: Path) -> dict[str, Any]:
    path = _run_file(run_id, out_dir)
    return json.loads(path.read_text(encoding="utf-8"))


def _gold_by_file(test_dir: Path) -> dict[str, dict[str, Any]]:
    gold_path = test_dir / "ground_truth.json"
    if not gold_path.is_file():
        return {}
    rows: list[dict[str, Any]] = json.loads(gold_path.read_text(encoding="utf-8"))
    return {row["file"]: row for row in rows if "file" in row}


def _run_summary(run_id: str, run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run_id,
        "timestamp": run.get("timestamp"),
        "prompt_version": run.get("prompt_version"),
        "prompt_hash": run.get("prompt_hash"),
        "model": run.get("model"),
        "total_cost_usd": run.get("total_cost_usd"),
        "n_docs": run.get("n_docs"),
        "n_errors": run.get("n_errors"),
        "overall_accuracy": run.get("overall_accuracy"),
        "overall_counts": run.get("overall_counts"),
    }


def _invoice_fields(gold: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in gold.items() if key not in _META_KEYS}


def _enrich_doc(
    doc: dict[str, Any], gold_row: dict[str, Any] | None
) -> dict[str, Any]:
    gold_invoice = _invoice_fields(gold_row) if gold_row else None
    pairs = []
    for field, ok in (doc.get("field_results") or {}).items():
        pairs.append(
            {
                "field": field,
                "ok": ok,
                "predicted": lookup_field(doc.get("extracted"), field),
                "gold": lookup_field(gold_invoice, field),
            }
        )
    return {**doc, "gold": gold_invoice, "field_pairs": pairs}


def _execute_eval(limit: int | None) -> None:
    try:
        run = run_eval(limit=limit, quiet=True, progress=eval_job.update_progress)
        eval_job.finish(run)
    except Exception as exc:
        eval_job.fail(f"{type(exc).__name__}: {exc}")


@app.get("/api/prompt")
def api_prompt() -> dict[str, Any]:
    return prompt_store.get_current()


@app.get("/api/prompts")
def api_prompts() -> list[dict[str, Any]]:
    return prompt_store.list_versions()


@app.get("/api/prompts/{version}")
def api_prompt_version(version: str) -> dict[str, Any]:
    try:
        return prompt_store.get_version(version)
    except KeyError:
        raise HTTPException(status_code=404, detail="Prompt version not found") from None


@app.post("/api/prompt")
def api_save_prompt(body: PromptSave) -> dict[str, Any]:
    try:
        return prompt_store.save_prompt(body.system_prompt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/runs")
def api_runs() -> list[dict[str, Any]]:
    out_dir = DEFAULT_OUT_DIR
    if not out_dir.is_dir():
        return []
    summaries: list[dict[str, Any]] = []
    for path in out_dir.glob("run_*.json"):
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summaries.append(_run_summary(path.stem, run))
    summaries.sort(key=lambda row: row.get("timestamp") or "", reverse=True)
    return summaries


@app.get("/api/runs/{run_id}")
def api_run_detail(run_id: str) -> dict[str, Any]:
    run = _load_run(run_id, DEFAULT_OUT_DIR)
    gold_map = _gold_by_file(DEFAULT_TEST_DIR)
    docs = [_enrich_doc(doc, gold_map.get(doc.get("file"))) for doc in run.get("docs") or []]
    return {
        **_run_summary(run_id, run),
        "per_field_accuracy": run.get("per_field_accuracy"),
        "per_field_counts": run.get("per_field_counts"),
        "by_style": run.get("by_style"),
        "system_prompt": run.get("system_prompt"),
        "docs": docs,
    }


@app.get("/api/eval/compare")
def api_compare(
    a: str = Query(..., min_length=1),
    b: str = Query(..., min_length=1),
) -> dict[str, Any]:
    left = _load_run(a, DEFAULT_OUT_DIR)
    right = _load_run(b, DEFAULT_OUT_DIR)
    return compare_runs(left, right, a_id=a, b_id=b)


@app.get("/api/eval/status")
def api_eval_status() -> dict[str, Any]:
    return eval_job.snapshot()


@app.post("/api/eval")
def api_start_eval(body: EvalStart) -> dict[str, Any]:
    if not eval_job.try_begin():
        raise HTTPException(status_code=409, detail="Eval already running")
    thread = threading.Thread(target=_execute_eval, args=(body.limit,), daemon=True)
    thread.start()
    return eval_job.snapshot()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
