"""Markdown and JSON execution reports for cleaning plans."""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.constants import APP_LOGGER_NAME
from app.preprocessing.audit import CleaningAudit
from app.preprocessing.exceptions import CleaningExecutionError

logger: logging.Logger = logging.getLogger(f"{APP_LOGGER_NAME}.preprocessing.report")


@dataclass(frozen=True)
class CleaningExecutionSummary:
    """Aggregate outcome of executing a plan against one dataset."""

    dataset_name: str
    status: str
    rows_before: int
    rows_after: int
    columns: tuple[str, ...]
    output_files: tuple[Path, ...]
    audits: tuple[CleaningAudit, ...]
    warnings: tuple[str, ...] = ()
    json_report: Path | None = None
    markdown_report: Path | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CleaningReportGenerator:
    """Persist execution summaries in JSON and Markdown formats."""

    def generate_json(
        self,
        summary: CleaningExecutionSummary,
        destination: Path,
        allowed_root: Path | None = None,
    ) -> Path:
        """Write a machine-readable execution report."""
        return self._write(
            destination,
            json.dumps(
                asdict(summary),
                default=self._json_default,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            allowed_root,
        )

    def generate_markdown(
        self,
        summary: CleaningExecutionSummary,
        destination: Path,
        allowed_root: Path | None = None,
    ) -> Path:
        """Write a human-readable execution report."""
        lines = [
            f"# Cleaning Execution: {summary.dataset_name}",
            "",
            f"- **Status:** {summary.status}",
            f"- **Generated:** {summary.timestamp.isoformat()}",
            f"- **Rows before:** {summary.rows_before}",
            f"- **Rows after:** {summary.rows_after}",
            f"- **Columns:** {', '.join(summary.columns) or 'None'}",
            "",
            "## Outputs",
            "",
        ]
        lines.extend(f"- `{path}`" for path in summary.output_files)
        lines.extend(["", "## File audit"])
        for audit in summary.audits:
            lines.extend(
                [
                    "",
                    f"### {audit.input_file.name}",
                    "",
                    f"- Status: {audit.status}",
                    f"- SHA-256: `{audit.dataset_hash}`",
                    f"- Output: `{audit.output_file}`",
                    f"- Rows: {audit.rows_before} → {audit.rows_after}",
                    f"- Duration (seconds): {audit.execution_duration_seconds:.6f}",
                ]
            )
        lines.extend(["", "## Warnings", ""])
        lines.extend(
            (f"- {warning}" for warning in summary.warnings)
            if summary.warnings
            else ("- None.",)
        )
        return self._write(
            destination,
            "\n".join(lines) + "\n",
            allowed_root,
        )

    @staticmethod
    def _json_default(value: object) -> str:
        """Serialize path and timestamp fields in execution reports."""
        if isinstance(value, (Path, datetime)):
            return value.isoformat() if isinstance(value, datetime) else str(value)
        raise TypeError(f"Unsupported execution report value: {type(value).__name__}")

    @staticmethod
    def _write(
        destination: Path,
        content: str,
        allowed_root: Path | None = None,
    ) -> Path:
        """Write a report and surface filesystem errors."""
        report_path = destination.expanduser()
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            if allowed_root is not None:
                root = allowed_root.expanduser().resolve()
                resolved_parent = report_path.parent.resolve()
                if not resolved_parent.is_relative_to(root):
                    raise CleaningExecutionError(
                        f"Report directory escapes interim root: {report_path.parent}"
                    )
            resolved_report = report_path.resolve()
            if not resolved_report.is_relative_to(report_path.parent.resolve()):
                raise CleaningExecutionError(
                    f"Report path escapes its output directory: {report_path}"
                )
            report_path.write_text(content, encoding="utf-8")
        except CleaningExecutionError:
            raise
        except OSError as exc:
            logger.exception("Unable to write cleaning report %s", report_path)
            raise CleaningExecutionError(
                f"Unable to write cleaning report {report_path}: {exc}"
            ) from exc

        logger.info("Generated cleaning report at %s", report_path)
        return report_path
