from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_config
from .extract import deterministic_run_id, infer_date_basis
from .profile import (
    profile_dataframe,
    summarise_pipeline,
    validation_reason_counts,
    write_profiling_report,
)
from .transform import (
    calculate_remaining_lease,
    create_resale_identifiers,
    flag_price_anomalies,
    hash_identifiers,
)
from .validate import build_reference_domains, validate_records


def _read_raw_file(path: Path, run_id: str) -> pd.DataFrame:
    """Read one raw CSV and attach processing lineage metadata."""
    df = pd.read_csv(path)
    df["_source_file"] = path.name
    df["_source_row_number"] = range(2, len(df) + 2)  # CSV header is line 1.
    df["_date_basis"] = infer_date_basis(path.name)
    df["_pipeline_run_id"] = run_id
    return df


def load_master(
    raw_dir: Path,
    start_month: str,
    end_month: str,
) -> tuple[pd.DataFrame, int, list[Path]]:
    """
    Read all raw CSVs, preserve lineage, and retain only the assessment period.

    Raw files themselves are never modified. Filtering and standardisation occur
    only after the files are read into the processing layer.
    """
    raw_paths = sorted(raw_dir.glob("*.csv"))

    if not raw_paths:
        raise FileNotFoundError(f"No CSV files found under {raw_dir}")

    run_id = deterministic_run_id(raw_paths)

    frames: list[pd.DataFrame] = []
    raw_rows = 0
    used_paths: list[Path] = []

    start = pd.Period(start_month, freq="M")
    end = pd.Period(end_month, freq="M")

    for path in raw_paths:
        df = _read_raw_file(path, run_id)
        raw_rows += len(df)

        if "month" not in df.columns:
            raise ValueError(f"Required column 'month' is missing from raw file: {path.name}")

        month_period = pd.PeriodIndex(df["month"], freq="M")
        mask = (month_period >= start) & (month_period <= end)

        if mask.any():
            frames.append(df.loc[mask].copy())
            used_paths.append(path)

    if not frames:
        raise ValueError(
            "No source rows overlap the configured assessment period "
            f"{start_month} to {end_month}"
        )

    master = pd.concat(frames, ignore_index=True, sort=False)

    return master, raw_rows, used_paths


def run_pipeline(
    project_root: str | Path,
    config_path: str | Path = "config.yaml",
    hash_secret: str | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    """
    Execute the HDB resale-flat ETL pipeline end-to-end.

    Pipeline stages:
    1. Read immutable raw inputs and retain lineage.
    2. Filter to Jan-2012 through Dec-2017.
    3. Build Jan-2012 authoritative validation domains.
    4. Validate and separate cleaned vs quarantined records.
    5. Calculate remaining lease and flag resale-price anomalies.
    6. Generate deterministic unique Resale Identifiers.
    7. De-identify identifiers using HMAC-SHA256.
    8. Write the five required output groups and markdown profiling report.
    """
    root = Path(project_root).resolve()

    config = load_config(root / config_path)
    pipe = config["pipeline"]
    paths = config["paths"]

    # ------------------------------------------------------------------
    # 1. Load and combine raw source data
    # ------------------------------------------------------------------
    master, raw_rows, used_paths = load_master(
        root / paths["raw"],
        pipe["start_month"],
        pipe["end_month"],
    )

    # ------------------------------------------------------------------
    # 2. Build strict Jan-2012 authoritative domains
    # ------------------------------------------------------------------
    reference_domains = build_reference_domains(
        master,
        pipe["authoritative_month"],
        pipe["authoritative_columns"],
    )

    # ------------------------------------------------------------------
    # 3. Validate / quarantine
    # ------------------------------------------------------------------
    cleaned, quarantined = validate_records(
        master,
        reference_domains,
        pipe["required_columns"],
        pipe["start_month"],
        pipe["end_month"],
        reference_year=pd.Timestamp(pipe["reference_date"]).year,
    )

    # ------------------------------------------------------------------
    # 4. Data enrichment and anomaly detection
    # ------------------------------------------------------------------
    cleaned = calculate_remaining_lease(
        cleaned,
        pipe["reference_date"],
        pipe["lease_years"],
    )

    anomaly_cfg = config["anomaly"]

    cleaned = flag_price_anomalies(
        cleaned,
        grouping_columns=anomaly_cfg["grouping_columns"],
        iqr_multiplier=float(anomaly_cfg["iqr_multiplier"]),
        min_group_size=int(anomaly_cfg["min_group_size"]),
    )

    # ------------------------------------------------------------------
    # 5. Resale Identifier generation
    # ------------------------------------------------------------------
    transformed = create_resale_identifiers(cleaned)

    # ------------------------------------------------------------------
    # 6. Identifier de-identification
    # ------------------------------------------------------------------
    secret = hash_secret or os.environ.get("HDB_HASH_SECRET")

    if secret is None:
        raise ValueError(
            "No HMAC secret supplied. Set HDB_HASH_SECRET or pass hash_secret "
            "explicitly; the secret must not be committed to Git."
        )

    hashed = hash_identifiers(transformed, secret)

    # ------------------------------------------------------------------
    # 7. Core correctness and reconciliation checks
    # ------------------------------------------------------------------
    if len(cleaned) + len(quarantined) != len(master):
        raise AssertionError(
            "Reconciliation failed: cleaned + quarantined != in-scope input"
        )

    if len(transformed) != len(cleaned):
        raise AssertionError(
            "Transformation row-count preservation failed: "
            "transformed rows != cleaned rows"
        )

    if len(hashed) != len(cleaned):
        raise AssertionError(
            "Hashing row-count preservation failed: hashed rows != cleaned rows"
        )

    if not transformed["resale_identifier"].is_unique:
        raise AssertionError(
            "Resale Identifier uniqueness requirement failed"
        )

    if "hashed_resale_identifier" in hashed.columns:
        if not hashed["hashed_resale_identifier"].is_unique:
            raise AssertionError(
                "Hashed identifier uniqueness requirement failed"
            )

    # ------------------------------------------------------------------
    # 8. Pipeline metrics and profiling objects
    # ------------------------------------------------------------------
    summary = summarise_pipeline(
        raw_rows=raw_rows,
        in_scope_rows=len(master),
        cleaned_rows=len(cleaned),
        quarantined_rows=len(quarantined),
        transformed_rows=len(transformed),
        hashed_rows=len(hashed),
        anomaly_rows=int(cleaned["resale_price_anomaly_flag"].sum()),
    )

    raw_profile = profile_dataframe(master)
    cleaned_profile = profile_dataframe(cleaned)
    quarantine_counts = validation_reason_counts(quarantined)

    result = {
        "master": master,
        "cleaned": cleaned,
        "quarantined": quarantined,
        "transformed": transformed,
        "hashed": hashed,
        "reference_domains": reference_domains,
        "raw_profile": raw_profile,
        "cleaned_profile": cleaned_profile,
        "quarantine_reason_counts": quarantine_counts,
        "summary": summary,
        "used_raw_files": [path.name for path in used_paths],
    }

    # ------------------------------------------------------------------
    # 9. Write required outputs and profiling report
    # ------------------------------------------------------------------
    if write_outputs:
        output_map = {
            "cleaned": root / paths["cleaned"],
            "transformed": root / paths["transformed"],
            "quarantined": root / paths["quarantined"],
            "hashed": root / paths["hashed"],
        }

        for key, destination in output_map.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            result[key].to_csv(destination, index=False)

        # Generate the markdown profiling report from the same pipeline state
        # as the output CSVs to keep documentation and data in sync.
        report_path = root / paths.get(
            "profiling_report",
            "reports/data_profiling_report.md",
        )

        write_profiling_report(
            report_path=report_path,
            summary=summary,
            raw_profile=raw_profile,
            cleaned_profile=cleaned_profile,
            quarantine_reason_counts=quarantine_counts,
            reference_domains=reference_domains,
            used_raw_files=[path.name for path in used_paths],
        )

    return result
