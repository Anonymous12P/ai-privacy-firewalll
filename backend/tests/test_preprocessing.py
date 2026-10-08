"""Tests for YAML policy loading and preprocessing-plan generation."""

from pathlib import Path

import pytest

from app.datasets import DatasetLoader, DatasetManifest, DatasetPipeline
from app.preprocessing.cleaning_policy import (
    CleaningPolicy,
    DuplicatePolicy,
    MissingValuePolicy,
    OutlierPolicy,
)
from app.preprocessing.config_loader import (
    load_cleaning_policy,
    load_preprocessing_config,
)
from app.preprocessing.exceptions import PreprocessingConfigError
from app.preprocessing.strategies import (
    describe_duplicate_strategy,
    describe_missing_strategy,
    describe_outlier_strategy,
)


def test_load_yaml_policy_and_preprocessing_configuration(
    tmp_path: Path,
) -> None:
    """YAML policy documents are parsed into typed validated models."""
    policy_path = tmp_path / "cleaning_policy.yaml"
    policy_path.write_text(
        "name: test-policy\n"
        'version: "1"\n'
        "missing_values:\n"
        "  strategy: constant\n"
        "  fill_value: 0\n"
        "duplicates:\n"
        "  strategy: keep_first\n"
        "outliers:\n"
        "  method: iqr\n"
        "  threshold: 2.0\n"
        "  strategy: flag\n"
        "columns: {}\n",
        encoding="utf-8",
    )
    preprocessing_path = tmp_path / "preprocessing.yaml"
    preprocessing_path.write_text(
        "enabled: true\n"
        "planning_only: false\n"
        "cleaning_policy_file: cleaning_policy.yaml\n"
        "stage_order: [duplicates, missing_values, outliers]\n",
        encoding="utf-8",
    )

    policy = load_cleaning_policy(policy_path)
    config = load_preprocessing_config(preprocessing_path)

    assert isinstance(policy, CleaningPolicy)
    assert policy.missing_values == MissingValuePolicy(
        strategy="constant",
        fill_value=0,
    )
    assert config.stage_order == ("duplicates", "missing_values", "outliers")


@pytest.mark.parametrize(
    "contents",
    (
        "name: invalid\nversion: '1'\nmissing_values:\n  strategy: erase\n",
        "- not-a-mapping\n",
        "name: missing-version\n",
    ),
)
def test_invalid_yaml_policy_is_rejected(tmp_path: Path, contents: str) -> None:
    """Unknown policy actions and malformed structures raise a typed error."""
    policy_path = tmp_path / "invalid.yaml"
    policy_path.write_text(contents, encoding="utf-8")

    with pytest.raises(PreprocessingConfigError):
        load_cleaning_policy(policy_path)


def test_missing_configuration_is_rejected(tmp_path: Path) -> None:
    """A missing YAML file raises a meaningful configuration exception."""
    with pytest.raises(PreprocessingConfigError, match="does not exist"):
        load_preprocessing_config(tmp_path / "missing.yaml")


def test_strategy_descriptors_are_created_without_cleaning() -> None:
    """Policy choices resolve into inert descriptors, not executable cleaners."""
    missing = describe_missing_strategy(
        MissingValuePolicy(strategy="constant", fill_value="unknown")
    )
    duplicates = describe_duplicate_strategy(
        DuplicatePolicy(strategy="keep_first", subset=("user",))
    )
    outliers = describe_outlier_strategy(
        OutlierPolicy(method="zscore", threshold=3.0, strategy="flag")
    )

    assert (missing.category, missing.strategy) == ("missing_values", "constant")
    assert (duplicates.category, duplicates.strategy) == ("duplicates", "keep_first")
    assert (outliers.category, outliers.strategy) == ("outliers", "flag")


def test_pipeline_generates_ordered_plan_without_modifying_csv(
    tmp_path: Path,
) -> None:
    """The full pipeline plans configured stages and leaves source bytes intact."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    source = data_dir / "events.csv"
    source.write_text(
        "user,age\nalice,20\nbob,\nalice,20\n",
        encoding="utf-8",
    )
    original_content = source.read_bytes()

    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "cleaning_policy.yaml").write_text(
        "name: test-policy\n"
        'version: "1"\n'
        "missing_values:\n"
        "  strategy: constant\n"
        "  fill_value: 0\n"
        "duplicates:\n"
        "  strategy: keep_first\n"
        "outliers:\n"
        "  method: iqr\n"
        "  threshold: 1.5\n"
        "  strategy: cap\n"
        "columns: {}\n",
        encoding="utf-8",
    )
    preprocessing_path = config_dir / "preprocessing.yaml"
    preprocessing_path.write_text(
        "enabled: true\n"
        "planning_only: false\n"
        "cleaning_policy_file: cleaning_policy.yaml\n"
        "stage_order: [duplicates, missing_values, outliers]\n",
        encoding="utf-8",
    )
    pipeline = DatasetPipeline(
        loader=DatasetLoader(data_dir=data_dir),
        interim_dir=tmp_path / "interim",
        preprocessing_config_path=preprocessing_path,
    )

    summary = pipeline.run(
        DatasetManifest(
            name="test-events",
            required_files=("events.csv",),
            required_columns={"events.csv": ("user", "age")},
        )
    )

    assert summary.dataset_name == "test-events"
    assert summary.status == "success"
    assert summary.rows_before == 3
    assert summary.rows_after == 2
    assert [path.parent.parent for path in summary.output_files] == [
        (tmp_path / "interim").resolve()
    ]
    assert summary.json_report is not None and summary.json_report.is_file()
    assert summary.markdown_report is not None and summary.markdown_report.is_file()
    assert source.read_bytes() == original_content


def test_default_yaml_examples_load() -> None:
    """Repository example policy and preprocessing files are valid."""
    config_dir = Path(__file__).resolve().parents[1] / "configs"
    config = load_preprocessing_config(config_dir / "preprocessing.yaml")
    policy = load_cleaning_policy(config_dir / config.cleaning_policy_file)

    assert config.planning_only is False
    assert policy.name == "cmu-cert-default"
