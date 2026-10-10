from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import numpy as np
import pandas as pd

AUTHORITATIVE_RULE_CODES = {
    "town": "INVALID_TOWN",
    "flat_type": "INVALID_FLAT_TYPE",
    "flat_model": "INVALID_FLAT_MODEL",
    "storey_range": "INVALID_STOREY_RANGE",
}


def build_reference_domains(
    master_df: pd.DataFrame,
    authoritative_month: str,
    authoritative_columns: Iterable[str],
) -> dict[str, set]:
    """Derive allowed categorical domains directly from the Jan-2012 authoritative slice."""
    reference = master_df.loc[master_df["month"].eq(authoritative_month)].copy()
    if reference.empty:
        raise ValueError(f"No rows found for authoritative month {authoritative_month}")
    domains = {
        column: set(reference[column].dropna().unique().tolist())
        for column in authoritative_columns
    }
    return domains


def _append_error(errors: list[list[str]], mask: pd.Series, code: str) -> None:
    for idx in np.flatnonzero(mask.to_numpy()):
        errors[idx].append(code)


def validate_records(
    df: pd.DataFrame,
    reference_domains: dict[str, set],
    required_columns: Iterable[str],
    start_month: str,
    end_month: str,
    reference_year: int = 2027,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply hard data-quality rules and split accepted vs quarantined rows.

    Statistical price anomalies are deliberately not hard failures; they are flagged later.
    """
    work = df.copy()
    errors: list[list[str]] = [[] for _ in range(len(work))]

    missing_columns = [c for c in required_columns if c not in work.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    for column in required_columns:
        _append_error(errors, work[column].isna(), f"MISSING_{column.upper()}")

    # Strict Jan-2012 reference domains.
    for column, allowed in reference_domains.items():
        invalid = work[column].notna() & ~work[column].isin(allowed)
        _append_error(errors, invalid, AUTHORITATIVE_RULE_CODES[column])

    # Month format and assessment-window integrity.
    month_parsed = pd.to_datetime(work["month"], format="%Y-%m", errors="coerce")
    _append_error(errors, month_parsed.isna(), "INVALID_MONTH_FORMAT")
    valid_month = month_parsed.notna()
    start_ts = pd.Timestamp(f"{start_month}-01")
    end_ts = pd.Timestamp(f"{end_month}-01")
    outside = valid_month & ((month_parsed < start_ts) | (month_parsed > end_ts))
    _append_error(errors, outside, "OUTSIDE_ASSESSMENT_WINDOW")

    # Numeric sanity rules. These reject impossible values, not merely unusual values.
    resale_price = pd.to_numeric(work["resale_price"], errors="coerce")
    floor_area = pd.to_numeric(work["floor_area_sqm"], errors="coerce")
    lease_year = pd.to_numeric(work["lease_commence_date"], errors="coerce")
    _append_error(errors, resale_price.isna() | (resale_price <= 0), "INVALID_RESALE_PRICE")
    _append_error(errors, floor_area.isna() | (floor_area <= 0), "INVALID_FLOOR_AREA")
    _append_error(
        errors,
        lease_year.isna() | (lease_year < 1900) | (lease_year > reference_year),
        "INVALID_LEASE_COMMENCE_DATE",
    )

    # Candidate duplicates: exact match on stable business fields excluding lineage and schema-evolution field.
    duplicate_columns = [
        "month", "town", "flat_type", "block", "street_name", "storey_range",
        "floor_area_sqm", "flat_model", "lease_commence_date", "resale_price",
    ]
    duplicate_mask = work.duplicated(subset=duplicate_columns, keep="first")
    _append_error(errors, duplicate_mask, "DUPLICATE_RECORD")

    work["validation_errors"] = ["|".join(row_errors) for row_errors in errors]
    work["validation_status"] = np.where(work["validation_errors"].eq(""), "PASS", "QUARANTINED")

    cleaned = work.loc[work["validation_status"].eq("PASS")].copy()
    quarantined = work.loc[work["validation_status"].eq("QUARANTINED")].copy()
    return cleaned, quarantined
