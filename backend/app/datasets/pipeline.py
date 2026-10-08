"""Dataset validation, profiling, and cleaning-plan orchestration."""

from dataclasses import replace
from pathlib import Path

from app.core.config import get_settings
from app.datasets.exceptions import DatasetValidationError
from app.datasets.loader import DatasetLoader
from app.datasets.profiler import DatasetProfiler
from app.datasets.schemas import DatasetManifest
from app.datasets.validator import DatasetValidator
from app.preprocessing.cleaning_engine import CleaningEngine
from app.preprocessing.cleaning_policy import CleaningPolicy
from app.preprocessing.config_loader import (
    load_cleaning_policy,
    load_preprocessing_config,
)
from app.preprocessing.cleaning_policy import PreprocessingConfig
from app.preprocessing.exceptions import CleaningExecutionError
from app.preprocessing.executor import CleaningExecutor
from app.preprocessing.report import (
    CleaningExecutionSummary,
    CleaningReportGenerator,
)


class DatasetPipeline:
    """Connect loading, validation, profiling, and planning-only cleaning."""

    def __init__(
        self,
        loader: DatasetLoader | None = None,
        validator: DatasetValidator | None = None,
        profiler: DatasetProfiler | None = None,
        cleaning_engine: CleaningEngine | None = None,
        cleaning_executor: CleaningExecutor | None = None,
        report_generator: CleaningReportGenerator | None = None,
        data_dir: Path | None = None,
        interim_dir: Path | None = None,
        cleaning_policy_path: Path | None = None,
        preprocessing_config_path: Path | None = None,
    ) -> None:
        """Initialize the pipeline and load its declarative YAML policies."""
        if validator is not None and data_dir is not None:
            raise ValueError("Provide data_dir through DatasetValidator.")
        if validator is not None and loader is not None:
            if validator.loader is not loader:
                raise ValueError("Pipeline loader and validator loader must match.")

        self.validator = validator or DatasetValidator(
            loader=loader,
            data_dir=data_dir,
        )
        self.loader = loader or self.validator.loader
        self.profiler = profiler or DatasetProfiler()
        self.cleaning_engine = cleaning_engine or CleaningEngine()
        settings = get_settings()
        self.raw_data_dir = settings.raw_data_dir
        self.interim_data_dir = interim_dir or settings.interim_data_dir
        self.cleaning_executor = cleaning_executor or CleaningExecutor()
        self.report_generator = report_generator or CleaningReportGenerator()

        config_dir = Path(__file__).resolve().parents[2] / "configs"
        config_path = preprocessing_config_path or config_dir / "preprocessing.yaml"
        self.preprocessing_config: PreprocessingConfig = load_preprocessing_config(
            config_path
        )
        policy_path = cleaning_policy_path or (
            config_path.parent / self.preprocessing_config.cleaning_policy_file
        )
        self.cleaning_policy: CleaningPolicy = load_cleaning_policy(policy_path)

    def run(self, manifest: DatasetManifest) -> CleaningExecutionSummary:
        """Validate, profile, plan, execute into interim, and write reports."""
        validation_result = self.validator.validate(manifest)
        if not validation_result.success:
            raise DatasetValidationError(
                f"Dataset validation failed for {manifest.name}.",
                validation_result,
            )

        profile_report = self.profiler.profile(
            manifest.name,
            validation_result.checked_files,
        )
        validation_warnings = tuple(
            issue.message for issue in validation_result.warnings
        )
        if validation_warnings:
            profile_report = replace(
                profile_report,
                warnings=validation_warnings + profile_report.warnings,
            )
        cleaning_plan = self.cleaning_engine.create_plan(
            profile_report,
            self.cleaning_policy,
            self.preprocessing_config,
        )
        if (
            not self.preprocessing_config.enabled
            or self.preprocessing_config.planning_only
        ):
            raise CleaningExecutionError(
                "Cleaning execution is disabled by preprocessing configuration."
            )

        execution_summary = self.cleaning_executor.execute(
            cleaning_plan,
            validation_result.checked_files,
            self.interim_data_dir,
            self.raw_data_dir,
        )
        dataset_report_dir = (
            execution_summary.output_files[0].parent
            if execution_summary.output_files
            else self.interim_data_dir / self._safe_dataset_name(manifest.name)
        )
        json_report = dataset_report_dir / "cleaning_report.json"
        markdown_report = dataset_report_dir / "cleaning_report.md"
        execution_summary = replace(
            execution_summary,
            json_report=json_report,
            markdown_report=markdown_report,
        )
        self.report_generator.generate_json(
            execution_summary,
            json_report,
            self.interim_data_dir,
        )
        self.report_generator.generate_markdown(
            execution_summary,
            markdown_report,
            self.interim_data_dir,
        )
        return execution_summary

    @staticmethod
    def _safe_dataset_name(name: str) -> str:
        """Create a safe single path component for report-only datasets."""
        import re

        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
        if not safe_name:
            raise CleaningExecutionError("Dataset name must not be empty.")
        return safe_name
