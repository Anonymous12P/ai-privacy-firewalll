"""Placeholder dataset schema and metadata definitions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetSchema:
    """Identify a future dataset schema without defining dataset fields."""

    name: str
    version: str

    # TODO: Add schema fields after dataset contracts are agreed upon.
