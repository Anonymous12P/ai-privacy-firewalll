"""Cleaning strategy contracts, descriptors, and execution implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

import pandas as pd
from app.preprocessing.cleaning_policy import (
    DuplicatePolicy,
    MissingValuePolicy,
    OutlierPolicy,
)

if TYPE_CHECKING:
    from app.preprocessing.cleaning_engine import CleaningPlanStep


@dataclass(frozen=True)
class StrategyDescriptor:
    """Describe a configured strategy for a future execution stage."""

    category: Literal["missing_values", "duplicates", "outliers"]
    strategy: str
    parameters: tuple[tuple[str, str | int | float | bool | None], ...]


class MissingValueStrategy(ABC):
    """Interface for a future missing-value strategy implementation."""

    @abstractmethod
    def describe(self, policy: MissingValuePolicy) -> StrategyDescriptor:
        """Describe a strategy; implementations must not be added in this sprint."""


class DuplicateStrategy(ABC):
    """Interface for a future duplicate-row strategy implementation."""

    @abstractmethod
    def describe(self, policy: DuplicatePolicy) -> StrategyDescriptor:
        """Describe a strategy; implementations must not be added in this sprint."""


class OutlierStrategy(ABC):
    """Interface for a future outlier strategy implementation."""

    @abstractmethod
    def describe(self, policy: OutlierPolicy) -> StrategyDescriptor:
        """Describe a strategy; implementations must not be added in this sprint."""


class DataFrameStrategy(ABC):
    """Interface for a concrete DataFrame operation selected by a plan step."""

    @abstractmethod
    def apply(
        self,
        dataframe: pd.DataFrame,
        step: CleaningPlanStep,
    ) -> tuple[pd.DataFrame, int]:
        """Apply one operation and return the result and changed-value count."""


class MeanMissingValueStrategy(DataFrameStrategy):
    """Fill selected numeric missing values with their column means."""

    def apply(
        self,
        dataframe: pd.DataFrame,
        step: CleaningPlanStep,
    ) -> tuple[pd.DataFrame, int]:
        return _fill_missing(dataframe, step, "mean")


class MedianMissingValueStrategy(DataFrameStrategy):
    """Fill selected numeric missing values with their column medians."""

    def apply(
        self,
        dataframe: pd.DataFrame,
        step: CleaningPlanStep,
    ) -> tuple[pd.DataFrame, int]:
        return _fill_missing(dataframe, step, "median")


class ModeMissingValueStrategy(DataFrameStrategy):
    """Fill selected missing values with the first deterministic mode."""

    def apply(
        self,
        dataframe: pd.DataFrame,
        step: CleaningPlanStep,
    ) -> tuple[pd.DataFrame, int]:
        return _fill_missing(dataframe, step, "mode")


class ConstantMissingValueStrategy(DataFrameStrategy):
    """Fill selected missing values with the configured constant."""

    def apply(
        self,
        dataframe: pd.DataFrame,
        step: CleaningPlanStep,
    ) -> tuple[pd.DataFrame, int]:
        fill_value = dict(step.parameters).get("fill_value")
        if fill_value is None:
            raise ValueError("Constant missing-value strategy needs fill_value.")
        result = dataframe.copy()
        missing_count = int(result.loc[:, list(step.columns)].isna().sum().sum())
        result.loc[:, list(step.columns)] = result.loc[
            :, list(step.columns)
        ].fillna(fill_value)
        return result, missing_count


class DropMissingValueStrategy(DataFrameStrategy):
    """Drop rows missing any selected column value."""

    def apply(
        self,
        dataframe: pd.DataFrame,
        step: CleaningPlanStep,
    ) -> tuple[pd.DataFrame, int]:
        result = dataframe.dropna(subset=list(step.columns)).copy()
        return result, len(dataframe) - len(result)


class DuplicateRemovalStrategy(DataFrameStrategy):
    """Remove duplicate rows according to an explicit keep policy."""

    def __init__(self, strategy: str) -> None:
        if strategy not in {"keep_first", "keep_last", "drop"}:
            raise ValueError(f"Unsupported duplicate strategy: {strategy}")
        self.strategy = strategy

    def apply(
        self,
        dataframe: pd.DataFrame,
        step: CleaningPlanStep,
    ) -> tuple[pd.DataFrame, int]:
        subset = list(step.columns) or None
        keep: Literal["first", "last", False]
        if self.strategy == "keep_first":
            keep = "first"
        elif self.strategy == "keep_last":
            keep = "last"
        else:
            keep = False
        result = dataframe.drop_duplicates(subset=subset, keep=keep).copy()
        return result, len(dataframe) - len(result)


class IqrOutlierStrategy(DataFrameStrategy):
    """Detect or handle numerical outliers using interquartile fences."""

    def apply(
        self,
        dataframe: pd.DataFrame,
        step: CleaningPlanStep,
    ) -> tuple[pd.DataFrame, int]:
        threshold = _numeric_parameter(step, "threshold", 1.5)
        return _apply_outlier_policy(dataframe, step, self._bounds, threshold)

    @staticmethod
    def _bounds(series: pd.Series, threshold: float) -> tuple[float, float]:
        first_quartile = float(series.quantile(0.25))
        third_quartile = float(series.quantile(0.75))
        spread = third_quartile - first_quartile
        return (
            first_quartile - threshold * spread,
            third_quartile + threshold * spread,
        )


class ZScoreOutlierStrategy(DataFrameStrategy):
    """Detect or handle numerical outliers using population z-scores."""

    def apply(
        self,
        dataframe: pd.DataFrame,
        step: CleaningPlanStep,
    ) -> tuple[pd.DataFrame, int]:
        threshold = _numeric_parameter(step, "threshold", 1.5)
        return _apply_outlier_policy(dataframe, step, self._bounds, threshold)

    @staticmethod
    def _bounds(series: pd.Series, threshold: float) -> tuple[float, float]:
        mean = float(series.mean())
        deviation = float(series.std(ddof=0))
        if deviation == 0:
            return float("-inf"), float("inf")
        return mean - threshold * deviation, mean + threshold * deviation


def _fill_missing(
    dataframe: pd.DataFrame,
    step: CleaningPlanStep,
    method: Literal["mean", "median", "mode"],
) -> tuple[pd.DataFrame, int]:
    """Fill selected columns using the requested column-wise statistic."""
    result = dataframe.copy()
    changed = 0
    for column in step.columns:
        missing = result[column].isna()
        changed += int(missing.sum())
        if method == "mean":
            fill_value = pd.to_numeric(result[column], errors="raise").mean()
        elif method == "median":
            fill_value = pd.to_numeric(result[column], errors="raise").median()
        else:
            modes = result[column].mode(dropna=True)
            if modes.empty:
                continue
            fill_value = modes.iloc[0]
        if pd.notna(fill_value):
            result.loc[missing, column] = fill_value
    return result, changed


def _numeric_parameter(
    step: CleaningPlanStep,
    name: str,
    default: float,
) -> float:
    """Read a finite numeric strategy parameter from a plan step."""
    value = dict(step.parameters).get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Strategy parameter {name!r} must be numeric.")
    return float(value)


def _apply_outlier_policy(
    dataframe: pd.DataFrame,
    step: CleaningPlanStep,
    calculate_bounds: Callable[[pd.Series, float], tuple[float, float]],
    threshold: float,
) -> tuple[pd.DataFrame, int]:
    """Apply flag, cap, or drop behavior without introducing derived columns."""
    strategy = step.strategy
    if strategy not in {"flag", "cap", "drop"}:
        raise ValueError(f"Unsupported outlier strategy: {strategy}")
    result = dataframe.copy()
    outlier_masks: dict[str, pd.Series] = {}
    bounds_by_column: dict[str, tuple[float, float]] = {}
    for column in step.columns:
        numeric = pd.to_numeric(result[column], errors="coerce")
        non_missing = numeric.dropna()
        if non_missing.empty:
            continue
        lower, upper = calculate_bounds(non_missing, threshold)
        bounds_by_column[column] = lower, upper
        outlier_masks[column] = (numeric < lower) | (numeric > upper)

    if strategy == "flag":
        return result, int(
            pd.concat(outlier_masks.values(), axis=1).any(axis=1).sum()
        ) if outlier_masks else 0
    if strategy == "drop":
        if not outlier_masks:
            return result, 0
        rows_to_drop = pd.concat(outlier_masks.values(), axis=1).any(axis=1)
        cleaned = result.loc[~rows_to_drop].copy()
        return cleaned, len(result) - len(cleaned)

    changed = 0
    for column, (lower, upper) in bounds_by_column.items():
        numeric = pd.to_numeric(result[column], errors="coerce")
        mask = outlier_masks[column]
        changed += int(mask.sum())
        result.loc[mask, column] = numeric.loc[mask].clip(lower=lower, upper=upper)
    return result, changed


def describe_missing_strategy(policy: MissingValuePolicy) -> StrategyDescriptor:
    """Build a data-free descriptor for the configured missing-value policy."""
    parameters: tuple[tuple[str, str | int | float | bool | None], ...] = (
        ("fill_value", policy.fill_value),
    )
    return StrategyDescriptor("missing_values", policy.strategy, parameters)


def describe_duplicate_strategy(policy: DuplicatePolicy) -> StrategyDescriptor:
    """Build a data-free descriptor for the configured duplicate policy."""
    parameters: tuple[tuple[str, str | int | float | bool | None], ...] = (
        ("subset", ",".join(policy.subset)),
    )
    return StrategyDescriptor("duplicates", policy.strategy, parameters)


def describe_outlier_strategy(policy: OutlierPolicy) -> StrategyDescriptor:
    """Build a data-free descriptor for the configured outlier policy."""
    parameters: tuple[tuple[str, str | int | float | bool | None], ...] = (
        ("method", policy.method),
        ("threshold", policy.threshold),
    )
    return StrategyDescriptor("outliers", policy.strategy, parameters)
