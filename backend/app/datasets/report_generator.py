"""JSON and Markdown serialization for dataset profile reports."""

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.core.constants import APP_LOGGER_NAME
from app.datasets.exceptions import DatasetProfileError
from app.datasets.schemas import ProfileReport

logger: logging.Logger = logging.getLogger(
    f"{APP_LOGGER_NAME}.datasets.report_generator"
)


class ProfileReportGenerator:
    """Render and write JSON or Markdown profile reports."""

    def generate_json(self, report: ProfileReport, destination: Path) -> Path:
        """Write a JSON profile report and return its destination."""
        payload = json.dumps(
            asdict(report),
            default=self._json_default,
            indent=2,
            ensure_ascii=False,
        )
        return self._write_report(report, destination, payload)

    def generate_markdown(self, report: ProfileReport, destination: Path) -> Path:
        """Write a Markdown profile report and return its destination."""
        return self._write_report(
            report,
            destination,
            self._render_markdown(report),
        )

    @staticmethod
    def _json_default(value: object) -> str:
        """Serialize paths and timestamps used by typed profile dataclasses."""
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"Unsupported profile report value: {type(value).__name__}")

    @staticmethod
    def _render_markdown(report: ProfileReport) -> str:
        """Render summary, per-file statistics, warnings, and recommendations."""
        lines = [
            f"# Dataset Profile: {report.dataset_name}",
            "",
            f"- **Generated:** {report.timestamp.isoformat()}",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
        ]
        lines.extend(
            f"| {metric.replace('_', ' ').title()} | {value} |"
            for metric, value in report.summary.items()
        )
        lines.extend(["", "## Statistics", ""])

        for profile in report.statistics:
            lines.extend(
                [
                    f"### {profile.file.name}",
                    "",
                    f"- Rows: {profile.row_count}",
                    f"- Columns: {profile.column_count}",
                    f"- Missing values: {profile.missing_values}",
                    f"- Duplicate rows: {profile.duplicate_rows}",
                    "",
                    "| Column | Type | Missing | Distinct | Count | Min | Max | Mean | "
                    "Top values |",
                    "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
                ]
            )
            for column in profile.columns:
                top_values = ", ".join(
                    f"{value} ({count})" for value, count in column.top_values
                )
                lines.append(
                    "| {name} | {data_type} | {missing} | {distinct} | {count} | "
                    "{minimum} | {maximum} | {mean} | {top_values} |".format(
                        name=column.name,
                        data_type=column.data_type,
                        missing=column.missing_count,
                        distinct=column.distinct_count,
                        count=column.numeric_count,
                        minimum=column.minimum if column.minimum is not None else "",
                        maximum=column.maximum if column.maximum is not None else "",
                        mean=column.mean if column.mean is not None else "",
                        top_values=top_values,
                    )
                )
            lines.append("")

        lines.extend(["## Warnings", ""])
        lines.extend(
            (f"- {warning}" for warning in report.warnings)
            if report.warnings
            else ("- None.",)
        )
        lines.extend(["", "## Recommendations", ""])
        lines.extend(
            (f"- {recommendation}" for recommendation in report.recommendations)
            if report.recommendations
            else ("- None.",)
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _write_report(
        report: ProfileReport,
        destination: Path,
        content: str,
    ) -> Path:
        """Create report parent directories, write text, and log completion."""
        report_path = destination.expanduser()
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            logger.exception("Unable to generate profile report at %s", report_path)
            raise DatasetProfileError(
                f"Unable to generate profile report at {report_path}: {exc}"
            ) from exc

        logger.info(
            "Generated profile report for %s at %s",
            report.dataset_name,
            report_path,
        )
        return report_path
