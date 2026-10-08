"""Tests for cleaning strategy execution, output safety, and audit reports."""

import hashlib
import json
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest

from app.preprocessing.audit import CleaningAuditWriter
from app.preprocessing.cleaning_engine import CleaningPlan, CleaningPlanStep
from app.preprocessing.exceptions import CleaningExecutionError
from app.preprocessing.executor import CleaningExecutor
from app.preprocessing.report import (
    CleaningExecutionSummary,
    CleaningReportGenerator,
)
from app.preprocessing.strategies import (
    ConstantMissingValueStrategy,
    DataFrameStrategy,
    DuplicateRemovalStrategy,
    DropMissingValueStrategy,
    IqrOutlierStrategy,
    MeanMissingValueStrategy,
    MedianMissingValueStrategy,
    ModeMissingValueStrategy,
    ZScoreOutlierStrategy,
)


def _step(
    stage: Literal["missing_values", "duplicates", "outliers"],
    strategy: str,
    columns: tuple[str, ...],
    **parameters: str | int | float | bool | None,
) -> CleaningPlanStep:
    """Create a simple typed plan step for strategy-focused tests."""
    return CleaningPlanStep(
        order=1,
        stage=stage,  # type: ignore[arg-type]
        strategy=strategy,
        columns=columns,
        parameters=tuple(parameters.items()),
    )


@pytest.mark.parametrize(
    ("strategy", "values", "expected", "parameters"),
    (
        (MeanMissingValueStrategy(), [1.0, None, 3.0], 2.0, ()),
        (MedianMissingValueStrategy(), [1.0, None, 9.0], 5.0, ()),
        (ModeMissingValueStrategy(), ["a", None, "a", "b"], "a", ()),
        (
            ConstantMissingValueStrategy(),
            ["x", None],
            "unknown",
            (("fill_value", "unknown"),),
        ),
    ),
)
def test_missing_value_fill_strategies(
    strategy: DataFrameStrategy,
    values: list[object],
    expected: object,
    parameters: tuple[tuple[str, str | int | float | bool | None], ...],
) -> None:
    """Mean, median, mode, and constant policies fill missing values."""
    dataframe = pd.DataFrame({"value": values})
    result, changed = strategy.apply(
        dataframe,
        CleaningPlanStep(
            order=1,
            stage="missing_values",
            strategy=(
                "constant"
                if isinstance(strategy, ConstantMissingValueStrategy)
                else "impute"
            ),
            columns=("value",),
            parameters=parameters,
        ),
    )

    assert changed == 1
    assert result.loc[1, "value"] == expected
    assert pd.isna(dataframe.loc[1, "value"])


def test_drop_missing_strategy() -> None:
    dataframe = pd.DataFrame({"value": [1.0, None, 3.0]})
    result, changed = DropMissingValueStrategy().apply(
        dataframe,
        _step("missing_values", "drop", ("value",)),
    )
    assert changed == 1
    assert len(result) == 2


@pytest.mark.parametrize(
    ("action", "expected"),
    (
        ("keep_first", [1, 2]),
        ("keep_last", [2, 1]),
        ("drop", [2]),
    ),
)
def test_duplicate_removal(action: str, expected: list[int]) -> None:
    dataframe = pd.DataFrame({"value": [1, 1, 2, 1]})
    result, changed = DuplicateRemovalStrategy(action).apply(
        dataframe,
        _step("duplicates", action, ("value",)),
    )
    assert result["value"].tolist() == expected
    assert changed == len(dataframe) - len(expected)


def test_iqr_cap_and_flag_do_not_add_columns() -> None:
    dataframe = pd.DataFrame({"value": [1.0, 1.0, 1.0, 100.0]})
    cap_step = _step(
        "outliers",
        "cap",
        ("value",),
        method="iqr",
        threshold=1.5,
    )
    result, changed = IqrOutlierStrategy().apply(dataframe, cap_step)
    assert changed == 1
    assert float(str(result.loc[3, "value"])) < 100
    assert list(result.columns) == ["value"]

    flag_step = _step(
        "outliers",
        "flag",
        ("value",),
        method="iqr",
        threshold=1.5,
    )
    flagged, count = IqrOutlierStrategy().apply(dataframe, flag_step)
    assert count == 1
    assert flagged.equals(dataframe)
    assert list(flagged.columns) == ["value"]


def test_zscore_drop_and_invalid_strategy() -> None:
    dataframe = pd.DataFrame({"value": [0.0, 0.0, 0.0, 100.0]})
    step = _step(
        "outliers",
        "drop",
        ("value",),
        method="zscore",
        threshold=1.5,
    )
    result, changed = ZScoreOutlierStrategy().apply(dataframe, step)
    assert changed == 1
    assert len(result) == 3

    executor = CleaningExecutor()
    with pytest.raises(CleaningExecutionError, match="Unsupported missing-value"):
        executor._apply_step(
            dataframe,
            _step("missing_values", "interpolate", ("value",)),
        )


def test_execution_writes_interim_output_and_sha256_audit(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    interim_dir = tmp_path / "interim"
    raw_dir.mkdir()
    source = raw_dir / "events.csv"
    source.write_text("value\n1\n\n2\n", encoding="utf-8")
    original_bytes = source.read_bytes()
    plan = CleaningPlan(
        dataset_name="events",
        steps=(),
        profile_summary=(("row_count", 2),),
    )
    summary = CleaningExecutor().execute(
        plan,
        (source,),
        interim_dir,
        raw_dir,
    )

    assert source.read_bytes() == original_bytes
    assert len(summary.output_files) == 1
    assert summary.output_files[0].is_relative_to(interim_dir.resolve())
    audit_path = summary.audits[0].output_file.parent / "audit"
    audit_file = next(audit_path.glob("*.audit.json"))
    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    assert audit["dataset_hash"] == hashlib.sha256(original_bytes).hexdigest()
    assert audit["status"] == "success"
    assert audit["input_file"] == str(source.resolve())
    assert audit["rows_before"] == summary.audits[0].rows_before
    assert audit["rows_after"] == summary.audits[0].rows_after
    assert "execution_duration_seconds" in audit


def test_output_directory_cannot_be_raw(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    plan = CleaningPlan("events", (), ())

    with pytest.raises(CleaningExecutionError, match="raw data directory"):
        CleaningExecutor().execute(plan, (), raw_dir, raw_dir)


def test_audit_and_execution_report_generation(tmp_path: Path) -> None:
    audit_path = tmp_path / "reports" / "audit.json"
    from datetime import datetime, timezone

    from app.preprocessing.audit import CleaningAudit

    audit = CleaningAudit(
        timestamp=datetime.now(timezone.utc),
        dataset_hash="a" * 64,
        input_file=Path("input.csv"),
        output_file=Path("output.csv"),
        rows_before=3,
        rows_after=2,
        columns=("a", "b"),
        execution_duration_seconds=0.25,
        status="success",
    )
    CleaningAuditWriter().write(audit, audit_path)
    assert json.loads(audit_path.read_text(encoding="utf-8"))["status"] == "success"

    summary = CleaningExecutionSummary(
        dataset_name="events",
        status="success",
        rows_before=3,
        rows_after=2,
        columns=("a", "b"),
        output_files=(Path("output.csv"),),
        audits=(audit,),
    )
    report_generator = CleaningReportGenerator()
    json_path = report_generator.generate_json(
        summary,
        tmp_path / "reports" / "execution.json",
    )
    markdown_path = report_generator.generate_markdown(
        summary,
        tmp_path / "reports" / "execution.md",
    )
    assert json.loads(json_path.read_text(encoding="utf-8"))["dataset_name"] == "events"
    assert "SHA-256" in markdown_path.read_text(encoding="utf-8")
