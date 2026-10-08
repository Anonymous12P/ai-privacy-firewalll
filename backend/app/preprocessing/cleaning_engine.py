"""Create ordered cleaning plans without executing data modifications."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from app.core.constants import APP_LOGGER_NAME
from app.preprocessing.cleaning_policy import (
    CleaningPolicy,
    PreprocessingConfig,
)
from app.preprocessing.strategies import (
    StrategyDescriptor,
    describe_duplicate_strategy,
    describe_missing_strategy,
    describe_outlier_strategy,
)

logger: logging.Logger = logging.getLogger(
    f"{APP_LOGGER_NAME}.preprocessing.cleaning_engine"
)

if TYPE_CHECKING:
    from app.datasets.schemas import ProfileReport


@dataclass(frozen=True)
class CleaningPlanStep:
    """One ordered, declarative operation for future execution."""

    order: int
    stage: Literal["missing_values", "duplicates", "outliers"]
    strategy: str
    columns: tuple[str, ...]
    parameters: tuple[tuple[str, str | int | float | bool | None], ...]


@dataclass(frozen=True)
class CleaningPlan:
    """An immutable plan; it contains no transformed dataset."""

    dataset_name: str
    steps: tuple[CleaningPlanStep, ...]
    profile_summary: tuple[tuple[str, int], ...]
    planning_only: Literal[True] = True
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CleaningEngine:
    """Derive deterministic ordered plan steps from profiles and policies."""

    def create_plan(
        self,
        profile: ProfileReport,
        policy: CleaningPolicy,
        config: PreprocessingConfig,
    ) -> CleaningPlan:
        """Prepare an ordered plan without loading or modifying dataset rows."""
        logger.info("Cleaning plan generation started for %s", profile.dataset_name)
        if not config.enabled:
            plan = self._build_plan(profile, ())
            logger.info(
                "Cleaning plan generated for %s with 0 planned step(s)",
                profile.dataset_name,
            )
            return plan

        numeric_columns = tuple(
            sorted(
                {
                    column.name
                    for dataset_profile in profile.statistics
                    for column in dataset_profile.columns
                    if column.data_type in {"integer", "float"}
                }
            )
        )
        columns_with_missing = tuple(
            sorted(
                {
                    column.name
                    for dataset_profile in profile.statistics
                    for column in dataset_profile.columns
                    if column.missing_count > 0
                }
            )
        )
        missing_steps = self._missing_value_steps(policy, columns_with_missing)
        outlier_steps = self._outlier_steps(policy, numeric_columns)
        steps_by_stage: dict[
            str,
            tuple[tuple[StrategyDescriptor, tuple[str, ...]], ...],
        ] = {
            "missing_values": missing_steps,
            "duplicates": (
                (
                    describe_duplicate_strategy(policy.duplicates),
                    tuple(sorted(policy.duplicates.subset)),
                ),
            ),
            "outliers": outlier_steps,
        }

        steps: list[CleaningPlanStep] = []
        for stage in config.stage_order:
            for descriptor, columns in steps_by_stage[stage]:
                if not self._stage_has_work(
                    stage,
                    descriptor,
                    columns,
                    profile,
                ):
                    continue
                steps.append(
                    CleaningPlanStep(
                        order=len(steps) + 1,
                        stage=stage,
                        strategy=descriptor.strategy,
                        columns=columns,
                        parameters=descriptor.parameters,
                    )
                )

        plan = self._build_plan(profile, tuple(steps))
        logger.info(
            "Cleaning plan generated for %s with %d planned step(s)",
            profile.dataset_name,
            len(plan.steps),
        )
        return plan

    @staticmethod
    def _missing_value_steps(
        policy: CleaningPolicy,
        observed_columns: tuple[str, ...],
    ) -> tuple[tuple[StrategyDescriptor, tuple[str, ...]], ...]:
        """Group observed columns by their effective missing-value policy."""
        grouped: dict[StrategyDescriptor, list[str]] = {}
        configured = set(policy.missing_values.columns)
        for name in observed_columns:
            override = policy.columns.get(name)
            column_policy = (
                override.missing_values if override is not None else None
            )
            effective_policy = column_policy or policy.missing_values
            if (
                column_policy is None
                and configured
                and name not in configured
            ):
                continue
            if effective_policy.strategy == "report_only":
                continue
            descriptor = describe_missing_strategy(effective_policy)
            grouped.setdefault(descriptor, []).append(name)
        return tuple(
            (descriptor, tuple(sorted(columns)))
            for descriptor, columns in grouped.items()
        )

    @staticmethod
    def _outlier_steps(
        policy: CleaningPolicy,
        numeric_columns: tuple[str, ...],
    ) -> tuple[tuple[StrategyDescriptor, tuple[str, ...]], ...]:
        """Group numeric columns by their effective outlier policy."""
        grouped: dict[StrategyDescriptor, list[str]] = {}
        configured = set(policy.outliers.columns)
        for name in numeric_columns:
            override = policy.columns.get(name)
            column_policy = override.outliers if override is not None else None
            effective_policy = column_policy or policy.outliers
            if column_policy is None and configured and name not in configured:
                continue
            if effective_policy.strategy == "report_only":
                continue
            descriptor = describe_outlier_strategy(effective_policy)
            grouped.setdefault(descriptor, []).append(name)
        return tuple(
            (descriptor, tuple(sorted(columns)))
            for descriptor, columns in grouped.items()
        )

    @staticmethod
    def _stage_has_work(
        stage: str,
        descriptor: StrategyDescriptor,
        columns: tuple[str, ...],
        profile: ProfileReport,
    ) -> bool:
        """Avoid proposing non-reporting actions when there is no observed target."""
        if descriptor.strategy == "report_only":
            return False
        if stage == "duplicates":
            return profile.summary.get("duplicate_rows", 0) > 0
        return bool(columns)

    @staticmethod
    def _build_plan(
        profile: ProfileReport,
        steps: tuple[CleaningPlanStep, ...],
    ) -> CleaningPlan:
        """Create an immutable declarative plan for the executor."""
        return CleaningPlan(
            dataset_name=profile.dataset_name,
            steps=steps,
            profile_summary=tuple(sorted(profile.summary.items())),
        )
