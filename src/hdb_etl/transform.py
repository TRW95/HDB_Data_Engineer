from __future__ import annotations

import hashlib
import hmac
import re

import numpy as np
import pandas as pd


def calculate_remaining_lease(
    df: pd.DataFrame,
    reference_date: str,
    lease_years: int = 99,
) -> pd.DataFrame:
    """Calculate lease remaining from year-only commencement data.

    Assumption: because the source provides only a commencement year, lease start is
    treated as 1 January of that year. This is explicit and reproducible; it also means
    the derived month component is normally zero for a 1-Jan reference date.
    """
    out = df.copy()
    reference = pd.Timestamp(reference_date)
    commencement_year = pd.to_numeric(out["lease_commence_date"], errors="coerce").astype("Int64")
    start = pd.to_datetime(commencement_year.astype("string") + "-01-01", errors="coerce")
    expiry = start + pd.DateOffset(years=lease_years)

    total_months = ((expiry.dt.year - reference.year) * 12 + (expiry.dt.month - reference.month)).clip(lower=0)
    out["remaining_lease_years_2027"] = (total_months // 12).astype("Int64")
    out["remaining_lease_months_2027"] = (total_months % 12).astype("Int64")
    out["remaining_lease_as_of_2027"] = (
        out["remaining_lease_years_2027"].astype("string")
        + " years "
        + out["remaining_lease_months_2027"].astype("string")
        + " months"
    )
    return out


def flag_price_anomalies(
    df: pd.DataFrame,
    grouping_columns: list[str],
    iqr_multiplier: float = 1.5,
    min_group_size: int = 20,
) -> pd.DataFrame:
    """Flag potentially anomalous prices using IQR within comparable cohorts.

    Outliers remain in the cleaned flow because an extreme transaction is not proof of bad data.
    """
    out = df.copy()
    out["year"] = out["month"].str[:4].astype(int)
    price = pd.to_numeric(out["resale_price"], errors="coerce")
    grouped = out.assign(_price=price).groupby(grouping_columns, dropna=False)["_price"]
    stats = grouped.agg(group_size="size", q1=lambda s: s.quantile(0.25), q3=lambda s: s.quantile(0.75)).reset_index()
    stats["iqr"] = stats["q3"] - stats["q1"]
    stats["price_lower_bound"] = stats["q1"] - iqr_multiplier * stats["iqr"]
    stats["price_upper_bound"] = stats["q3"] + iqr_multiplier * stats["iqr"]

    out = out.merge(stats, on=grouping_columns, how="left", validate="many_to_one")
    # Re-read price after merge because merge resets/reorders the index labels.
    price = pd.to_numeric(out["resale_price"], errors="coerce")
    enough_data = out["group_size"] >= min_group_size
    out["resale_price_anomaly_flag"] = enough_data & (
        (price < out["price_lower_bound"]) | (price > out["price_upper_bound"])
    )
    out["resale_price_anomaly_reason"] = np.select(
        [
            ~enough_data,
            enough_data & (price < out["price_lower_bound"]),
            enough_data & (price > out["price_upper_bound"]),
        ],
        ["INSUFFICIENT_GROUP_SIZE", "BELOW_IQR_BOUND", "ABOVE_IQR_BOUND"],
        default="WITHIN_IQR_BOUND",
    )
    return out


def _block_component(value: object) -> str:
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        raise ValueError(f"Block has no numerical characters: {value!r}")
    return digits[:3].zfill(3)


def _average_price_component(value: float) -> str:
    # Requirement says first three digits; flooring avoids introducing rounding-driven digit changes.
    digits = re.sub(r"\D", "", str(int(np.floor(value))))
    return digits[:3].zfill(3)


def create_resale_identifiers(df: pd.DataFrame) -> pd.DataFrame:
    """Build the prescribed identifier and resolve collisions deterministically."""
    out = df.copy()
    group_cols = ["month", "town", "flat_type"]
    avg_price = (
        out.groupby(group_cols, dropna=False)["resale_price"]
        .mean()
        .rename("group_avg_resale_price")
        .reset_index()
    )
    out = out.merge(avg_price, on=group_cols, how="left", validate="many_to_one")
    out["_block_component"] = out["block"].map(_block_component)
    out["_avg_price_component"] = out["group_avg_resale_price"].map(_average_price_component)
    out["_yymm_component"] = out["month"].str[2:4] + out["month"].str[5:7]
    out["_town_component"] = out["town"].str.strip().str[0].str.upper()

    out["base_resale_identifier"] = (
        "S"
        + out["_block_component"]
        + out["_avg_price_component"]
        + out["_yymm_component"]
        + out["_town_component"]
    )

    # Stable ordering uses source lineage, not current dataframe position.
    sort_cols = ["base_resale_identifier", "_source_file", "_source_row_number"]
    order = out.sort_values(sort_cols, kind="stable").index
    collision_size = out.groupby("base_resale_identifier")["base_resale_identifier"].transform("size")
    sequence = pd.Series(index=out.index, dtype="Int64")
    sequence.loc[order] = (
        out.loc[order].groupby("base_resale_identifier", sort=False).cumcount().add(1).astype("Int64")
    )
    out["identifier_collision_size"] = collision_size.astype(int)
    out["identifier_collision_sequence"] = sequence
    out["resale_identifier"] = np.where(
        out["identifier_collision_size"].gt(1),
        out["base_resale_identifier"] + "-" + out["identifier_collision_sequence"].astype(str).str.zfill(3),
        out["base_resale_identifier"],
    )

    helper_cols = ["_block_component", "_avg_price_component", "_yymm_component", "_town_component"]
    return out.drop(columns=helper_cols)


def hmac_identifier(identifier: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), identifier.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_identifiers(df: pd.DataFrame, secret: str) -> pd.DataFrame:
    """Irreversibly pseudonymise the identifier with keyed HMAC-SHA256."""
    if not secret or len(secret) < 16:
        raise ValueError("HDB_HASH_SECRET must be set to a non-trivial secret (>=16 characters).")
    out = df.copy()
    out["hashed_resale_identifier"] = out["resale_identifier"].map(lambda value: hmac_identifier(value, secret))
    if not out["hashed_resale_identifier"].is_unique:
        raise AssertionError("Hashed identifier uniqueness check failed")
    # Hashed output must not expose the clear-text identifiers used to derive it.
    return out.drop(columns=["resale_identifier", "base_resale_identifier"])
