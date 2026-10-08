"""Structured JSON audit records for cleaning executions."""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from app.core.constants import APP_LOGGER_NAME
from app.preprocessing.exceptions import CleaningExecutionError

logger: logging.Logger = logging.getLogger(f"{APP_LOGGER_NAME}.preprocessing.audit")


@dataclass(frozen=True)
class CleaningAudit:
    """Auditable metadata for one cleaned input file."""

    timestamp: datetime
    dataset_hash: str
    input_file: Path
    output_file: Path
    rows_before: int
    rows_after: int
    columns: tuple[str, ...]
    execution_duration_seconds: float
    status: str


class CleaningAuditWriter:
    """Write audit data as JSON without embedding source row values."""

    def write(self, audit: CleaningAudit, destination: Path) -> Path:
        """Persist an audit JSON document to the supplied destination."""
        audit_path = destination.expanduser()
        try:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_root = audit_path.parent.resolve()
            if not audit_path.resolve().is_relative_to(audit_root):
                raise CleaningExecutionError(
                    f"Audit path escapes its output directory: {audit_path}"
                )
            audit_path.write_text(
                json.dumps(
                    asdict(audit),
                    default=self._json_default,
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.exception("Unable to write cleaning audit %s", audit_path)
            raise CleaningExecutionError(
                f"Unable to write cleaning audit {audit_path}: {exc}"
            ) from exc

        logger.info("Generated cleaning audit at %s", audit_path)
        return audit_path

    @staticmethod
    def _json_default(value: object) -> str:
        """Serialize path and timestamp fields in an audit."""
        if isinstance(value, (Path, datetime)):
            return value.isoformat() if isinstance(value, datetime) else str(value)
        raise TypeError(f"Unsupported audit value: {type(value).__name__}")
