# doc-extractor

Invoice PDFs → structured, validated data via Claude.

Text-first extraction with a vision fallback for scanned or sparse PDFs. Output is a typed `Invoice` (vendor, customer, line items, totals) with a second pass that checks the arithmetic.

## Setup

Python 3.14+. Set `ANTHROPIC_API_KEY`.

```bash
uv sync --group dev
```

## Commands

```bash
uv run doc-extractor path/to/invoice.pdf
uv run doc-extractor-eval [--limit N]
uv run doc-extractor-lab
uv run pytest
```

The lab (`http://127.0.0.1:8000`) is for editing the system prompt, running the eval set, and inspecting misses. Evals score against `test_data/ground_truth.json` and write artifacts to `eval_runs/`.
