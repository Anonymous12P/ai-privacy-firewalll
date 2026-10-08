"""Unit tests for dataset structure and CSV header validation."""

from pathlib import Path

import pytest

from app.datasets import (
    DatasetLoader,
    DatasetManifest,
    DatasetPipeline,
    DatasetValidator,
)


def test_missing_required_file_is_reported(tmp_path: Path) -> None:
    """Required files absent from a dataset directory cause validation failure."""
    result = DatasetValidator(loader=DatasetLoader(data_dir=tmp_path)).validate(
        DatasetManifest(name="cmu-cert", required_files=("logon.csv",))
    )

    assert not result.success
    assert any(issue.code == "missing_required_file" for issue in result.errors)
    assert result.checked_files == ()


def test_empty_directory_is_reported(tmp_path: Path) -> None:
    """A directory with no dataset files fails validation."""
    result = DatasetValidator(loader=DatasetLoader(data_dir=tmp_path)).validate(
        DatasetManifest(name="cmu-cert")
    )

    assert not result.success
    assert any(issue.code == "empty_dataset_directory" for issue in result.errors)


def test_invalid_extension_is_reported(tmp_path: Path) -> None:
    """Files outside the manifest's allowed extensions fail validation."""
    (tmp_path / "notes.txt").write_text("not a dataset", encoding="utf-8")
    result = DatasetValidator(loader=DatasetLoader(data_dir=tmp_path)).validate(
        DatasetManifest(name="cmu-cert", allowed_extensions=(".csv",))
    )

    assert not result.success
    assert any(issue.code == "invalid_file_extension" for issue in result.errors)


def test_empty_file_is_reported(tmp_path: Path) -> None:
    """Zero-byte files fail validation without being opened."""
    (tmp_path / "logon.csv").touch()
    result = DatasetValidator(loader=DatasetLoader(data_dir=tmp_path)).validate(
        DatasetManifest(name="cmu-cert")
    )

    assert not result.success
    assert any(issue.code == "empty_file" for issue in result.errors)


def test_missing_required_columns_are_reported_from_header(
    tmp_path: Path,
) -> None:
    """CSV header validation reports required columns that are absent."""
    (tmp_path / "logon.csv").write_text(
        "user,date\nuser-1,2024-01-01\n",
        encoding="utf-8",
    )
    result = DatasetValidator(loader=DatasetLoader(data_dir=tmp_path)).validate(
        DatasetManifest(
            name="cmu-cert",
            required_files=("logon.csv",),
            required_columns={"logon.csv": ("user", "pc")},
        )
    )

    assert not result.success
    issue = next(
        issue for issue in result.errors
        if issue.code == "missing_required_columns"
    )
    assert "pc" in issue.message


def test_successful_validation_checks_manifest_and_csv_header(
    tmp_path: Path,
) -> None:
    """Valid required files and headers produce a successful result."""
    dataset_file = tmp_path / "logon.csv"
    dataset_file.write_text(
        "user,pc,date\nuser-1,workstation-1,2024-01-01\n",
        encoding="utf-8",
    )
    pipeline = DatasetPipeline(
        loader=DatasetLoader(data_dir=tmp_path),
        interim_dir=tmp_path / "interim",
    )

    result = pipeline.run(
        DatasetManifest(
            name="cmu-cert",
            required_files=("logon.csv",),
            required_columns={"logon.csv": ("user", "pc", "date")},
        )
    )

    assert result.dataset_name == "cmu-cert"
    assert result.status == "success"
    assert result.rows_before == 1
    assert result.rows_after == 1
    assert result.output_files[0].is_file()


def test_validation_does_not_parse_csv_data_rows(tmp_path: Path) -> None:
    """Malformed content after the first row does not affect header validation."""
    (tmp_path / "logon.csv").write_text(
        'user,pc\n"unterminated quoted data row',
        encoding="utf-8",
    )
    result = DatasetValidator(loader=DatasetLoader(data_dir=tmp_path)).validate(
        DatasetManifest(
            name="cmu-cert",
            required_columns={"logon.csv": ("user", "pc")},
        )
    )

    assert result.success
    assert result.errors == ()


def test_dataset_directory_must_exist(tmp_path: Path) -> None:
    """Validator reports unavailable configured directories as a result."""
    result = DatasetValidator(data_dir=tmp_path / "missing").validate(
        DatasetManifest(name="cmu-cert")
    )

    assert not result.success
    assert any(issue.code == "invalid_dataset_directory" for issue in result.errors)


def test_non_csv_file_is_not_parsed_as_csv(tmp_path: Path) -> None:
    """Allowed non-CSV formats receive filesystem checks only."""
    (tmp_path / "records.jsonl").write_text('{"id": 1}\n', encoding="utf-8")
    result = DatasetValidator(loader=DatasetLoader(data_dir=tmp_path)).validate(
        DatasetManifest(name="external-records", allowed_extensions=(".jsonl",))
    )

    assert result.success
    assert len(result.checked_files) == 1


@pytest.mark.parametrize("filename", ("../outside.csv", "", "."))
def test_manifest_rejects_unsafe_required_paths(
    tmp_path: Path,
    filename: str,
) -> None:
    """Unsafe required paths are recorded as validation errors."""
    result = DatasetValidator(loader=DatasetLoader(data_dir=tmp_path)).validate(
        DatasetManifest(name="cmu-cert", required_files=(filename,))
    )

    assert not result.success
    assert any(issue.code == "invalid_required_file_path" for issue in result.errors)
