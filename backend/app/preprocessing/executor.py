"""Safe execution of configured cleaning plans into the interim data area."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.core.constants import APP_LOGGER_NAME
from app.preprocessing.audit import CleaningAudit, CleaningAuditWriter
from app.preprocessing.cleaning_engine import CleaningPlan, CleaningPlanStep
from app.preprocessing.exceptions import CleaningExecutionError
from app.preprocessing.report import CleaningExecutionSummary
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

logger: logging.Logger = logging.getLogger(
    f"{APP_LOGGER_NAME}.preprocessing.executor"
)

@dataclass(frozen=True)
class _FileExecution:
    """Internal result for one input file."""

    audit: CleaningAudit
    warnings: tuple[str, ...]


class CleaningExecutor:
    """Apply planned dataframe strategies and persist outputs only in interim."""

    def __init__(self, audit_writer: CleaningAuditWriter | None = None) -> None:
        self.audit_writer = audit_writer or CleaningAuditWriter()

    def execute(
        self,
        plan: CleaningPlan,
        input_files: Iterable[Path],
        interim_dir: Path,
        raw_dir: Path,
    ) -> CleaningExecutionSummary:
        """Execute an ordered plan and write cleaned files beneath interim."""
        logger.info("Cleaning execution started for %s", plan.dataset_name)
        raw_root = raw_dir.expanduser().resolve()
        interim_root = interim_dir.expanduser().resolve()
        if interim_root == raw_root or interim_root.is_relative_to(raw_root):
            raise CleaningExecutionError(
                "Interim output directory must not be the raw data directory "
                "or a subdirectory of it."
            )
        interim_root.mkdir(parents=True, exist_ok=True)
        dataset_dir = interim_root / self._safe_name(plan.dataset_name)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        resolved_dataset_dir = dataset_dir.resolve()
        if (
            not resolved_dataset_dir.is_relative_to(interim_root)
            or resolved_dataset_dir == raw_root
            or resolved_dataset_dir.is_relative_to(raw_root)
        ):
            raise CleaningExecutionError(
                f"Dataset output directory is unsafe: {dataset_dir}"
            )
        audit_dir = resolved_dataset_dir / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        resolved_audit_dir = audit_dir.resolve()
        if (
            not resolved_audit_dir.is_relative_to(interim_root)
            or resolved_audit_dir == raw_root
            or resolved_audit_dir.is_relative_to(raw_root)
        ):
            raise CleaningExecutionError(
                f"Audit directory is unsafe: {audit_dir}"
            )

        audits: list[CleaningAudit] = []
        outputs: list[Path] = []
        warnings: list[str] = []
        total_rows_before = 0
        total_rows_after = 0
        all_columns: set[str] = set()
        all_input_files = tuple(input_files)
        csv_files = tuple(
            path for path in all_input_files if path.suffix.casefold() == ".csv"
        )
        for input_path in csv_files:
            execution = self._execute_file(
                plan,
                input_path,
                resolved_dataset_dir,
                resolved_audit_dir,
                raw_root,
            )
            audits.append(execution.audit)
            outputs.append(execution.audit.output_file)
            warnings.extend(execution.warnings)
            total_rows_before += execution.audit.rows_before
            total_rows_after += execution.audit.rows_after
            all_columns.update(execution.audit.columns)

        if len(csv_files) != len(all_input_files):
            warnings.append("Non-CSV input files were not processed.")
        if not csv_files:
            raise CleaningExecutionError(
                f"No CSV files were available to execute for {plan.dataset_name}."
            )

        summary = CleaningExecutionSummary(
            dataset_name=plan.dataset_name,
            status="success",
            rows_before=total_rows_before,
            rows_after=total_rows_after,
            columns=tuple(sorted(all_columns)),
            output_files=tuple(outputs),
            audits=tuple(audits),
            warnings=tuple(warnings),
        )
        logger.info(
            "Cleaning execution completed for %s: files=%d, rows=%d->%d",
            plan.dataset_name,
            len(outputs),
            total_rows_before,
            total_rows_after,
        )
        return summary

    def execute_dataframe(
        self,
        dataframe: pd.DataFrame,
        plan: CleaningPlan,
    ) -> tuple[pd.DataFrame, tuple[str, ...]]:
        """Apply ordered plan steps to a copy and return the cleaned DataFrame."""
        result = dataframe.copy()
        warnings: list[str] = []
        for step in sorted(plan.steps, key=lambda item: item.order):
            result, affected = self._apply_step(result, step)
            if step.stage == "outliers" and step.strategy == "flag" and affected:
                warnings.append(
                    f"Flagged {affected} outlier row(s) for columns "
                    f"{', '.join(step.columns)}; no flag columns were added."
                )
        return result, tuple(warnings)

    def _execute_file(
        self,
        plan: CleaningPlan,
        input_path: Path,
        output_dir: Path,
        audit_dir: Path,
        raw_root: Path,
    ) -> _FileExecution:
        """Transform a single CSV in memory, then atomically persist its copy."""
        input_file = input_path.expanduser().resolve()
        if not input_file.is_file():
            raise CleaningExecutionError(f"Input dataset file does not exist: {input_file}")

        started_at = time.perf_counter()
        timestamp = datetime.now(timezone.utc)
        dataset_hash = self._sha256(input_file)
        output_name = (
            f"{self._safe_name(input_file.stem)}-{dataset_hash[:12]}.cleaned.csv"
        )
        output_path = (output_dir / output_name).resolve()
        if (
            not output_path.is_relative_to(output_dir)
            or output_path == input_file
            or output_path == raw_root
            or output_path.is_relative_to(raw_root)
        ):
            raise CleaningExecutionError(
                f"Cleaning output path escapes interim directory: {output_path}"
            )

        dataframe: pd.DataFrame | None = None
        temp_path: Path | None = None
        try:
            dataframe = pd.read_csv(input_file)
            rows_before = len(dataframe)
            dataframe, operation_warnings = self.execute_dataframe(dataframe, plan)

            output_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".tmp",
                prefix=".cleaning-",
                dir=output_dir,
                delete=False,
            ) as temporary_file:
                temp_path = Path(temporary_file.name)
            dataframe.to_csv(temp_path, index=False)
            os.replace(temp_path, output_path)
            temp_path = None
            duration = time.perf_counter() - started_at
            audit = CleaningAudit(
                timestamp=timestamp,
                dataset_hash=dataset_hash,
                input_file=input_file,
                output_file=output_path,
                rows_before=rows_before,
                rows_after=len(dataframe),
                columns=tuple(str(column) for column in dataframe.columns),
                execution_duration_seconds=duration,
                status="success",
            )
            audit_path = audit_dir / f"{output_name}.audit.json"
            self.audit_writer.write(audit, audit_path)
            logger.info(
                "Cleaned dataset loaded and written from %s to %s",
                input_file,
                output_path,
            )
            return _FileExecution(audit, tuple(operation_warnings))
        except (
            CleaningExecutionError,
            OSError,
            UnicodeError,
            pd.errors.ParserError,
            ValueError,
            KeyError,
        ) as exc:
            logger.exception("Cleaning execution failed for %s", input_file)
            rows = len(dataframe) if dataframe is not None else 0
            failed_audit = CleaningAudit(
                timestamp=timestamp,
                dataset_hash=dataset_hash,
                input_file=input_file,
                output_file=output_path,
                rows_before=rows,
                rows_after=rows,
                columns=(
                    tuple(str(column) for column in dataframe.columns)
                    if dataframe is not None
                    else ()
                ),
                execution_duration_seconds=time.perf_counter() - started_at,
                status="failed",
            )
            self.audit_writer.write(
                failed_audit,
                audit_dir / f"{output_name}.audit.json",
            )
            if isinstance(exc, CleaningExecutionError):
                raise
            raise CleaningExecutionError(
                f"Cleaning execution failed for {input_file}: {exc}"
            ) from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    @classmethod
    def _apply_step(
        cls,
        dataframe: pd.DataFrame,
        step: CleaningPlanStep,
    ) -> tuple[pd.DataFrame, int]:
        """Dispatch a typed plan step to its concrete strategy."""
        if not isinstance(step, CleaningPlanStep):
            raise CleaningExecutionError("Cleaning plan contains an invalid step.")
        if step.stage == "missing_values":
            strategy = {
                "mean": MeanMissingValueStrategy,
                "median": MedianMissingValueStrategy,
                "mode": ModeMissingValueStrategy,
                "constant": ConstantMissingValueStrategy,
                "drop": DropMissingValueStrategy,
            }.get(step.strategy)
            if strategy is None:
                raise CleaningExecutionError(
                    f"Unsupported missing-value strategy: {step.strategy}"
                )
            columns = cls._available_columns(dataframe, step)
            if not columns:
                return dataframe, 0
            return strategy().apply(dataframe, cls._with_columns(step, columns))

        if step.stage == "duplicates":
            if step.strategy not in {"keep_first", "keep_last", "drop"}:
                raise CleaningExecutionError(
                    f"Unsupported duplicate strategy: {step.strategy}"
                )
            columns = cls._available_columns(dataframe, step)
            if step.columns and not columns:
                return dataframe, 0
            return DuplicateRemovalStrategy(step.strategy).apply(
                dataframe,
                cls._with_columns(step, columns),
            )

        if step.stage == "outliers":
            method = dict(step.parameters).get("method")
            strategy_type: type[DataFrameStrategy]
            if method == "iqr":
                strategy_type = IqrOutlierStrategy
            elif method == "zscore":
                strategy_type = ZScoreOutlierStrategy
            else:
                raise CleaningExecutionError(
                    f"Unsupported outlier method: {method}"
                )
            if step.strategy not in {"flag", "cap", "drop"}:
                raise CleaningExecutionError(
                    f"Unsupported outlier strategy: {step.strategy}"
                )
            columns = cls._available_columns(dataframe, step)
            if not columns:
                return dataframe, 0
            return strategy_type().apply(
                dataframe,
                cls._with_columns(step, columns),
            )

        raise CleaningExecutionError(f"Unsupported cleaning stage: {step.stage}")

    @staticmethod
    def _available_columns(
        dataframe: pd.DataFrame,
        step: CleaningPlanStep,
    ) -> tuple[str, ...]:
        """Select columns present in this file; fail on no configured columns."""
        columns = step.columns
        if not columns:
            return tuple(str(column) for column in dataframe.columns)
        available = tuple(column for column in columns if column in dataframe.columns)
        return available

    @staticmethod
    def _with_columns(
        step: CleaningPlanStep,
        columns: tuple[str, ...],
    ) -> CleaningPlanStep:
        """Build a step narrowed to columns present in the current file."""
        if not isinstance(step, CleaningPlanStep):
            raise CleaningExecutionError("Cleaning plan contains an invalid step.")
        return CleaningPlanStep(
            order=step.order,
            stage=step.stage,
            strategy=step.strategy,
            columns=columns,
            parameters=step.parameters,
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        """Hash input bytes in bounded chunks for an audit record."""
        digest = hashlib.sha256()
        try:
            with path.open("rb") as input_file:
                for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise CleaningExecutionError(
                f"Unable to hash input dataset {path}: {exc}"
            ) from exc
        return digest.hexdigest()

    @staticmethod
    def _safe_name(value: str) -> str:
        """Restrict dataset and file names used in output paths."""
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
        if not safe_name:
            raise CleaningExecutionError("Dataset and file names must be non-empty.")
        return safe_name
