# Dataset Architecture

Dataset infrastructure provides configured locations, file discovery,
structural validation, and read-only profiling. Validation reads CSV headers;
profiling streams dataset rows to calculate descriptive statistics without
modifying or transforming source files.

## Directory structure

```text
backend/
├── .env
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── external/
├── configs/
│   ├── cleaning_policy.yaml
│   └── preprocessing.yaml
└── app/
    ├── core/
    │   └── config.py
    ├── datasets/
    │   ├── __init__.py
    │   ├── loader.py
    │   ├── exceptions.py
    │   ├── validator.py
    │   ├── schemas.py
    │   ├── pipeline.py
    │   ├── profiler.py
    │   └── report_generator.py
    └── preprocessing/
        ├── __init__.py
        ├── config_loader.py
        ├── cleaning_policy.py
        ├── strategies.py
        ├── cleaning_engine.py
        ├── executor.py
        ├── audit.py
        └── report.py
```

The `DATA_ROOT` configuration defaults to `backend/data/`. Unless overridden
individually, the four configured directories are resolved beneath that root:
`RAW_DATA_DIR`, `INTERIM_DATA_DIR`, `PROCESSED_DATA_DIR`, and
`EXTERNAL_DATA_DIR`. All configuration values are `pathlib.Path` objects and
can be overridden with environment variables or the backend `.env` file.

### Data folders

- `backend/data/raw/` is reserved for source datasets in their original,
  unmodified form.
- `backend/data/interim/` is reserved for temporary or intermediate
  representations produced during a future dataset workflow.
- `backend/data/processed/` is reserved for finalized datasets prepared for
  future application or model use.
- `backend/data/external/` is reserved for reference data or other inputs
  obtained from external sources.

Dataset folders are not populated by the application. Git tracks the empty
directories with `.gitkeep` files; dataset contents are ignored to avoid
committing data files.

## `DatasetLoader`

`DatasetLoader` in `backend/app/datasets/loader.py` manages filesystem paths
within one configured dataset directory. By default it uses `RAW_DATA_DIR`;
callers may select another configured directory by passing it at construction.
It does not read file contents, and does not perform preprocessing, cleaning,
feature engineering, or model training.

### Responsibilities and methods

- `dataset_exists(filename)` checks whether a requested regular file exists.
- `list_available_files()` lists regular files directly within the configured
  directory.
- `get_dataset_path(filename)` resolves a safe path without opening the file.
- `validate_required_files(required_files)` confirms all requested files exist
  and returns their resolved paths.
- Initialization checks that the selected directory exists and is a
  directory. Paths that escape the selected root are rejected.

Filesystem failures use typed exceptions from `exceptions.py`. The loader logs
initialization, directory and file failures, discovery, and successful
validation through the application logger hierarchy.

### Validation and profiling lifecycle

`DatasetPipeline.run(manifest)` passes the manifest to `DatasetValidator`.
The validator uses `DatasetLoader` to verify the configured directory,
discover files, resolve required filenames, and check that required files are
present. It then checks allowed extensions and file sizes. For CSV files it
reads only the header row.

All validation checks are accumulated into one `ValidationResult`. If
validation fails, the pipeline raises `DatasetValidationError` with the
validation result and does not profile. After successful validation,
`DatasetProfiler` streams each validated CSV and computes row and column
counts, missing values, duplicate rows, inferred types, numeric statistics,
and up to ten top categorical values per categorical column.

Profiling does not alter source data. Non-CSV files allowed by the manifest
are skipped with a warning. Profiling filesystem, decoding, and malformed-row
failures raise `DatasetProfileError`.

After profiling, `CleaningEngine` consumes the typed profile, policy, and
preprocessing configuration to create an ordered `CleaningPlan`. The plan
contains declarative stages and parameters only; the planner itself never
modifies dataset values.

When `planning_only` is false, the pipeline passes the plan and validated
source paths to `CleaningExecutor`. It reads CSV files into DataFrames, applies
only configured operations, and writes new CSV artifacts under the configured
`INTERIM_DATA_DIR`. Raw inputs are read-only and are never output targets.
When `planning_only` is true, execution is rejected.

## Manifest and results

`DatasetManifest` is an immutable dataclass describing one dataset. It
contains a dataset `name`, `required_files` (relative filenames),
`allowed_extensions` (default `.csv`), and `required_columns`, a mapping from
relative filename to the tuple of required CSV column names. Required columns
are optional until the authoritative CMU CERT file/column contract is defined.

`ValidationIssue` records a stable issue `code`, a human-readable `message`,
`severity` (`warning` or `error`), and an optional affected `file`.
`ValidationResult` records `success`, warning and error issue tuples,
`checked_files`, and a UTC `timestamp`. `success` is false if any errors were
collected. Warnings do not fail validation. A CSV without a configured
required-column list is checked for a non-empty header and reported with a
`required_columns_not_configured` warning.

The validator logs the start and completion of each run, every file checked,
and any warnings or errors. The loader continues to log filesystem operations.

## Profile results and generated reports

`ColumnProfile` holds each column's inferred type, missing and distinct counts,
numeric count/minimum/maximum/mean when applicable, and categorical top values.
`DatasetProfile` aggregates these statistics for one file. `ProfileReport`
combines per-file profiles with dataset-level summary counts, warnings,
recommendations, and a UTC timestamp.

`ProfileReportGenerator.generate_json(report, destination)` writes a
machine-readable JSON report. `generate_markdown(report, destination)` writes a
human-readable Markdown report. Both create the destination's parent directory
when needed. Reports include dataset name, summary, per-column statistics,
warnings, recommendations, and timestamp.

## Configuration-driven preprocessing

YAML configuration lives in `backend/configs/`:

- `preprocessing.yaml` controls whether a plan is generated, whether execution
  is disabled with `planning_only`, identifies the cleaning policy file, and
  declares stage order.
- `cleaning_policy.yaml` contains dataset-wide and per-column missing-value,
  duplicate, and outlier policies.

`config_loader.py` uses safe YAML loading and strict typed Pydantic models.
Missing files, malformed YAML, unknown fields, and unsupported values raise
`PreprocessingConfigError`; invalid configuration is not silently defaulted.
The example policy uses `report_only` actions, so it proposes no cleaning
modifications; the execution stage still writes an auditable copy to interim.

Policy types are `MissingValuePolicy`, `DuplicatePolicy`, `OutlierPolicy`,
`ColumnPolicy`, and `CleaningPolicy`. The abstract contracts in
`strategies.py` defines `MissingValueStrategy`, `DuplicateStrategy`, and
`OutlierStrategy` planning interfaces, plus concrete DataFrame strategy
implementations. Strategy descriptors record requested actions and parameters
for the plan.

`CleaningEngine.create_plan(profile, policy, config)` honors the configured
stage order and observed profile. Its `CleaningPlan` is a declarative object;
`PreprocessingConfig.planning_only` controls whether the pipeline may submit
the plan to the execution engine. The repository example sets
`enabled: true` and `planning_only: false` to enable execution. Otherwise, the
pipeline raises `CleaningExecutionError` before reading any input CSV for
cleaning.

### Execution engine and strategy implementations

`CleaningExecutor` sorts plan steps by order, reads validated CSV inputs,
applies configured operations to in-memory DataFrames, and atomically writes
new CSV files under `INTERIM_DATA_DIR/<dataset>/`. It rejects interim output
roots inside the configured raw directory and ensures the resolved output
destination remains in interim. Raw source files are never written.

Concrete strategy implementations are limited to the YAML-supported actions:

- Missing values: drop rows, or fill selected columns with mean, median, mode,
  or a constant.
- Duplicates: retain first, retain last, or remove every member of a duplicate
  group.
- Outliers: calculate IQR or population Z-score thresholds; flag counts in
  execution warnings without adding feature columns, cap values, or drop rows.

Per-column policy overrides are represented as separate ordered plan steps.
Unsupported steps fail with `CleaningExecutionError`. No feature engineering,
training, or model code is involved.

### Execution audit and reports

`CleaningAuditWriter` creates one JSON audit record per input file under the
interim dataset's `audit/` subdirectory. Each record contains a UTC timestamp,
SHA-256 hash of the original input bytes, input/output paths, row counts before
and after, output columns, execution duration in seconds, and success/failure
status. Audit records do not include source row contents.

`CleaningReportGenerator` writes `cleaning_report.json` and
`cleaning_report.md` alongside the interim output. The reports summarize the
dataset, row/column counts, outputs, audit details, warnings, status, and
timestamp.

## Dataset modules

- `loader.py` implements filesystem-only dataset discovery and required-file
  checks.
- `exceptions.py` defines dataset infrastructure exception types.
- `validator.py` validates directories, required files, extensions, empty
  files, and CSV headers.
- `schemas.py` defines typed manifests, validation issues/results, and profile
  result dataclasses.
- `profiler.py` reads validated CSV records to calculate descriptive
  statistics, without modifying source data.
- `report_generator.py` serializes profile results as JSON and Markdown.
- `preprocessing/config_loader.py` reads and validates preprocessing YAML.
- `preprocessing/cleaning_policy.py` defines typed policy models.
- `preprocessing/strategies.py` defines abstract strategy contracts and inert
  descriptors.
- `preprocessing/cleaning_engine.py` creates ordered, execution-disabled
  declarative cleaning plans.
- `preprocessing/executor.py` executes supported plan steps into interim.
- `preprocessing/audit.py` writes per-file JSON audit records.
- `preprocessing/report.py` writes JSON and Markdown execution reports.
- `pipeline.py` connects loader, validator, profiler, planner, executor, and
  report generation; validation failure blocks all later stages.
- `__init__.py` defines the package's public dataset interfaces.

## Future cleaning stage

Future extensions may add carefully reviewed strategies, stricter resource
limits, and transactional multi-file execution. Feature engineering and model
training remain out of scope.
The concrete CMU CERT required files and column sets should be added to a
manifest once the selected dataset release is specified.
