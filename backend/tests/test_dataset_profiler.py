"""Unit tests for read-only dataset profiling and report generation."""

import json
from pathlib import Path

import pytest

from app.datasets import (
    DatasetLoader,
    DatasetManifest,
    DatasetPipeline,
    DatasetProfiler,
    DatasetValidationError,
    ProfileReportGenerator,
    DatasetValidator,
)


def _validated_report(tmp_path: Path):
    """Build a small temporary dataset and return its pipeline profile."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "events.csv").write_text(
        "user,age,score,category\n"
        "alice,20,1.5,A\n"
        "bob,30,2.5,B\n"
        "alice,20,1.5,A\n"
        "carol,,3.0,A\n",
        encoding="utf-8",
    )
    loader = DatasetLoader(data_dir=tmp_path)
    validation = DatasetValidator(loader=loader).validate(
        DatasetManifest(
            name="temporary-events",
            required_files=("events.csv",),
            required_columns={"events.csv": ("user", "age", "score", "category")},
        )
    )
    assert validation.success
    return DatasetProfiler().profile("temporary-events", validation.checked_files)


def test_profile_missing_values_and_duplicate_rows(tmp_path: Path) -> None:
    """Profiles report missing cells and exact duplicate records."""
    report = _validated_report(tmp_path)

    assert report.summary["row_count"] == 4
    assert report.summary["missing_values"] == 1
    assert report.summary["duplicate_rows"] == 1
    assert report.recommendations
    assert report.statistics[0].missing_values == 1
    assert report.statistics[0].duplicate_rows == 1


def test_profile_numeric_and_categorical_statistics(tmp_path: Path) -> None:
    """Profiles expose numeric aggregates and the most common categories."""
    report = _validated_report(tmp_path)
    columns = {column.name: column for column in report.statistics[0].columns}

    assert report.statistics[0].column_count == 4
    assert columns["age"].data_type == "integer"
    assert columns["age"].numeric_count == 3
    assert columns["age"].minimum == 20
    assert columns["age"].maximum == 30
    assert columns["age"].mean == pytest.approx(70 / 3)
    assert columns["score"].data_type == "float"
    assert columns["score"].minimum == 1.5
    assert columns["score"].maximum == 3.0
    assert columns["score"].mean == pytest.approx(2.125)
    assert columns["category"].data_type == "string"
    assert columns["category"].top_values == (("A", 3), ("B", 1))


def test_categorical_top_values_are_limited_to_ten(tmp_path: Path) -> None:
    """Categorical reports bound the displayed values to the requested limit."""
    source = tmp_path / "categories.csv"
    rows = "".join(f"value-{index}\n" for index in range(12))
    source.write_text(f"category\n{rows}", encoding="utf-8")
    report = DatasetProfiler().profile("categories", (source.resolve(),))

    assert len(report.statistics[0].columns[0].top_values) == 10


def test_profiling_preserves_source_values_for_duplicate_counts(
    tmp_path: Path,
) -> None:
    """Whitespace-distinct source rows are not normalized into duplicates."""
    source = tmp_path / "whitespace.csv"
    source.write_text("category\nvalue\n value \n", encoding="utf-8")
    original_content = source.read_bytes()

    profile = DatasetProfiler().profile("whitespace", (source.resolve(),))

    assert profile.statistics[0].duplicate_rows == 0
    assert source.read_bytes() == original_content


def test_report_generator_writes_json_and_markdown(tmp_path: Path) -> None:
    """Generated reports include summary, statistics, warnings and guidance."""
    report = _validated_report(tmp_path / "dataset")
    output_dir = tmp_path / "reports"
    generator = ProfileReportGenerator()

    json_path = generator.generate_json(report, output_dir / "profile.json")
    markdown_path = generator.generate_markdown(
        report,
        output_dir / "profile.md",
    )

    json_report = json.loads(json_path.read_text(encoding="utf-8"))
    markdown_report = markdown_path.read_text(encoding="utf-8")
    assert json_report["dataset_name"] == "temporary-events"
    assert json_report["summary"]["duplicate_rows"] == 1
    assert "timestamp" in json_report
    assert "Recommendations" in markdown_report
    assert "Statistics" in markdown_report
    assert "temporary-events" in markdown_report


def test_pipeline_does_not_profile_failed_validation(tmp_path: Path) -> None:
    """A failed validation blocks profiling and carries its typed result."""
    pipeline = DatasetPipeline(loader=DatasetLoader(data_dir=tmp_path))

    with pytest.raises(DatasetValidationError) as error:
        pipeline.run(
            DatasetManifest(
                name="missing-dataset",
                required_files=("absent.csv",),
            )
        )

    assert not error.value.validation_result.success
