"""Typed, validated policy models for future dataset cleaning."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictPolicyModel(BaseModel):
    """Shared strict settings for YAML-backed policy models."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class MissingValuePolicy(StrictPolicyModel):
    """Declare a future missing-value action without executing it."""

    strategy: Literal["report_only", "drop", "constant", "mean", "median", "mode"] = (
        "report_only"
    )
    fill_value: str | int | float | None = None
    columns: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_fill_value(self) -> "MissingValuePolicy":
        """Require a fill value for constant replacement policies."""
        if self.strategy == "constant" and self.fill_value is None:
            raise ValueError("fill_value is required when strategy is 'constant'.")
        return self


class DuplicatePolicy(StrictPolicyModel):
    """Declare how duplicate rows may be handled in a future cleaning stage."""

    strategy: Literal["report_only", "keep_first", "keep_last", "drop"] = (
        "report_only"
    )
    subset: tuple[str, ...] = ()


class OutlierPolicy(StrictPolicyModel):
    """Declare an outlier detection/action policy without applying it."""

    method: Literal["iqr", "zscore"] = "iqr"
    threshold: float = Field(default=1.5, gt=0)
    strategy: Literal["report_only", "flag", "cap", "drop"] = "report_only"
    columns: tuple[str, ...] = ()

    @field_validator("threshold")
    @classmethod
    def validate_finite_threshold(cls, value: float) -> float:
        """Reject non-finite thresholds that cannot be interpreted safely."""
        if not math.isfinite(value):
            raise ValueError("threshold must be a finite number.")
        return value


class ColumnPolicy(StrictPolicyModel):
    """Declare optional per-column overrides for cleaning policies."""

    missing_values: MissingValuePolicy | None = None
    outliers: OutlierPolicy | None = None


class CleaningPolicy(StrictPolicyModel):
    """Declare dataset-wide and per-column cleaning policy."""

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    missing_values: MissingValuePolicy = Field(
        default_factory=MissingValuePolicy
    )
    duplicates: DuplicatePolicy = Field(default_factory=DuplicatePolicy)
    outliers: OutlierPolicy = Field(default_factory=OutlierPolicy)
    columns: dict[str, ColumnPolicy] = Field(default_factory=dict)

    @field_validator("columns")
    @classmethod
    def validate_column_names(
        cls,
        value: dict[str, ColumnPolicy],
    ) -> dict[str, ColumnPolicy]:
        """Reject blank column names in per-column policy mappings."""
        if any(not name.strip() for name in value):
            raise ValueError("Per-column policy names must not be empty.")
        return value


class PreprocessingConfig(StrictPolicyModel):
    """Control ordered cleaning and whether the execution stage is enabled."""

    enabled: bool = True
    planning_only: bool = False
    cleaning_policy_file: str = "cleaning_policy.yaml"
    stage_order: tuple[
        Literal["missing_values", "duplicates", "outliers"],
        ...,
    ] = ("missing_values", "duplicates", "outliers")

    @field_validator("cleaning_policy_file")
    @classmethod
    def validate_policy_file(cls, value: str) -> str:
        """Require a non-empty policy filename."""
        if not value.strip():
            raise ValueError("cleaning_policy_file must not be empty.")
        return value

    @field_validator("stage_order")
    @classmethod
    def validate_stage_order(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require each planning stage to occur at most once."""
        if len(value) != len(set(value)):
            raise ValueError("stage_order must not contain duplicate stages.")
        return value
