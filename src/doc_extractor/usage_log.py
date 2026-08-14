"""Log Anthropic API token usage and estimated cost to a local CSV.

Attach once at client creation; call sites stay as normal SDK usage:

    client = instrument(Anthropic())
    client.messages.create(...)
    with labeled("extract"):
        client.messages.parse(...)
"""

import csv
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any

# USD per million tokens: (input, output)
# Approximate / time-sensitive — Sonnet 5 intro pricing through 2026-08-31; update after that.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}

DEFAULT_PRICE = (3.0, 15.0)
LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "api_usage.csv"
CSV_FIELDS = [
    "timestamp",
    "model",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "label",
]

# ContextVar = request-scoped label (like AsyncLocalStorage / AsyncLocal) without threading args.
_label: ContextVar[str] = ContextVar("usage_label", default="")


@contextmanager
def labeled(label: str) -> Iterator[None]:
    """Optionally tag subsequent API calls in the CSV log."""
    token = _label.set(label)
    try:
        yield
    finally:
        _label.reset(token)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    key = model.split("@")[0]
    input_rate, output_rate = PRICES_PER_MTOK.get(key, DEFAULT_PRICE)
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def log_usage(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    label: str | None = None,
    path: Path = LOG_PATH,
) -> float:
    label = _label.get() if label is None else label
    cost = estimate_cost(model, input_tokens, output_tokens)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": f"{cost:.6f}",
                "label": label,
            }
        )

    print(
        f"\n[usage] {model} in={input_tokens} out={output_tokens} "
        f"cost=${cost:.6f}" + (f" ({label})" if label else "") + "\n"
    )
    return cost


def _log_message(message: Any, model: str | None = None) -> None:
    usage = message.usage
    log_usage(
        model=model or getattr(message, "model", "unknown"),
        input_tokens=int(usage.input_tokens),
        output_tokens=int(usage.output_tokens),
    )


def instrument(client: Any) -> Any:
    """Wrap messages.create / stream / parse so every call is usage-logged.

    Monkey-patch keeps call sites as normal SDK usage instead of a custom wrapper API.
    """
    messages = client.messages
    original_create = messages.create
    original_stream = messages.stream
    original_parse = messages.parse

    @wraps(original_create)
    def create(*args: Any, **kwargs: Any) -> Any:
        message = original_create(*args, **kwargs)
        _log_message(message, model=kwargs.get("model"))
        return message

    @contextmanager
    @wraps(original_stream)
    def stream(*args: Any, **kwargs: Any) -> Iterator[Any]:
        with original_stream(*args, **kwargs) as s:
            yield s
            _log_message(s.get_final_message(), model=kwargs.get("model"))

    @wraps(original_parse)
    def parse(*args: Any, **kwargs: Any) -> Any:
        message = original_parse(*args, **kwargs)
        _log_message(message, model=kwargs.get("model"))
        return message

    messages.create = create  # type: ignore[method-assign]
    messages.stream = stream  # type: ignore[method-assign]
    messages.parse = parse  # type: ignore[method-assign]
    return client
