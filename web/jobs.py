"""Single in-process eval job. One-at-a-time because runs share the API key and cost budget."""

import threading
from copy import deepcopy
from pathlib import Path
from typing import Any


class EvalJob:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {"status": "idle"}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state)

    def try_begin(self) -> bool:
        with self._lock:
            if self._state.get("status") == "running":
                return False
            self._state = {
                "status": "running",
                "progress": {
                    "done": 0,
                    "total": 0,
                    "current_file": None,
                    "n_errors": 0,
                },
                "run_id": None,
                "error": None,
                "summary": None,
            }
            return True

    def update_progress(self, progress: dict[str, Any]) -> None:
        with self._lock:
            if self._state.get("status") == "running":
                self._state["progress"] = progress

    def finish(self, run: dict[str, Any]) -> None:
        artifact = run.get("artifact") or ""
        run_id = Path(artifact).stem if artifact else None
        with self._lock:
            self._state = {
                "status": "done",
                "progress": self._state.get("progress"),
                "run_id": run_id,
                "error": None,
                "summary": {
                    "prompt_version": run.get("prompt_version"),
                    "overall_accuracy": run.get("overall_accuracy"),
                    "n_docs": run.get("n_docs"),
                    "n_errors": run.get("n_errors"),
                    "total_cost_usd": run.get("total_cost_usd"),
                    "artifact": artifact,
                },
            }

    def fail(self, message: str) -> None:
        with self._lock:
            self._state["status"] = "error"
            self._state["error"] = message

    def reset(self) -> None:
        """Test helper so cases do not leak running state."""
        with self._lock:
            self._state = {"status": "idle"}
