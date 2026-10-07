# Dataset Architecture

This sprint establishes dataset storage locations and Python interfaces only.
No dataset is loaded, validated, transformed, or otherwise processed by the
current implementation.

## Directory structure

```text
backend/
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── external/
└── app/
    └── datasets/
        ├── __init__.py
        ├── loader.py
        ├── validator.py
        ├── schemas.py
        └── pipeline.py
```

### Data folders

- `backend/data/raw/` is reserved for source datasets in their original,
  unmodified form.
- `backend/data/interim/` is reserved for temporary or intermediate
  representations produced during a future dataset workflow.
- `backend/data/processed/` is reserved for finalized datasets prepared for
  future application or model use.
- `backend/data/external/` is reserved for reference data or other inputs
  obtained from external sources.

These folders are currently empty and are not read by the application. Git
tracks the empty directories with `.gitkeep` files; dataset contents are
ignored to avoid committing data files.

## Planned data flow

When implemented, a dataset workflow is expected to accept a source from
`raw/` or `external/`, perform any explicitly designed intermediate work in
`interim/`, and place approved outputs in `processed/`. The loader, validator,
and pipeline currently expose placeholders only. There is no loading,
preprocessing, cleaning, feature engineering, or model-training behavior.

## Dataset modules

- `loader.py` will own the interface for locating and loading a dataset from a
  supplied source.
- `validator.py` will own the interface for checking a dataset against
  requirements defined in the future.
- `schemas.py` will hold dataset schema and metadata definitions as those
  requirements become available.
- `pipeline.py` will coordinate a future dataset workflow by using the
  separately defined dataset interfaces.
- `__init__.py` defines the package's public dataset interfaces.

The Python interfaces currently raise `NotImplementedError` when invoked, so
they cannot silently appear to load or process data.
