"""Cost sink used by the eval runner."""

from pathlib import Path

from doc_extractor.usage_log import capturing_usage, log_usage


def test_capturing_usage_nests_and_totals(tmp_path: Path) -> None:
    log_path = tmp_path / "usage.csv"
    with capturing_usage() as outer:
        with capturing_usage() as inner:
            cost = log_usage(
                model="claude-sonnet-4-5",
                input_tokens=1_000_000,
                output_tokens=0,
                path=log_path,
            )
        assert cost == 3.0
        assert inner == [3.0]
        assert outer == [3.0]
