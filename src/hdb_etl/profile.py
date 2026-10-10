from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd


def profile_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return a compact per-column profile suitable for reporting."""
    rows = []

    for column in df.columns:
        series = df[column]

        profile = {
            "column": column,
            "dtype": str(series.dtype),
            "rows": len(series),
            "null_count": int(series.isna().sum()),
            "null_pct": round(float(series.isna().mean() * 100), 3),
            "distinct_count": int(series.nunique(dropna=True)),
        }

        # Add useful numeric statistics where applicable.
        if pd.api.types.is_numeric_dtype(series):
            non_null = series.dropna()
            if not non_null.empty:
                profile.update(
                    {
                        "min": float(non_null.min()),
                        "max": float(non_null.max()),
                        "mean": round(float(non_null.mean()), 3),
                        "median": round(float(non_null.median()), 3),
                    }
                )

        rows.append(profile)

    return pd.DataFrame(rows)


def top_values(df: pd.DataFrame, column: str, n: int = 10) -> pd.DataFrame:
    """Return the most common values for a column."""
    counts = df[column].value_counts(dropna=False).head(n)
    return counts.rename_axis(column).reset_index(name="count")


def validation_reason_counts(quarantine_df: pd.DataFrame) -> pd.DataFrame:
    """Count individual validation failures from pipe-delimited error strings."""
    counter: Counter[str] = Counter()

    if "validation_errors" in quarantine_df.columns:
        for value in quarantine_df["validation_errors"].dropna().astype(str):
            for reason in filter(None, value.split("|")):
                counter[reason] += 1

    return pd.DataFrame(
        counter.most_common(),
        columns=["validation_rule", "row_count"],
    )


def summarise_pipeline(
    raw_rows: int,
    in_scope_rows: int,
    cleaned_rows: int,
    quarantined_rows: int,
    transformed_rows: int,
    hashed_rows: int,
    anomaly_rows: int,
) -> dict[str, int]:
    """Return key pipeline reconciliation and quality metrics."""
    return {
        "raw_rows_across_selected_files": raw_rows,
        "in_scope_rows": in_scope_rows,
        "cleaned_rows": cleaned_rows,
        "quarantined_rows": quarantined_rows,
        "transformed_rows": transformed_rows,
        "hashed_rows": hashed_rows,
        "price_anomaly_rows": anomaly_rows,
    }


def _format_reference_domains(reference_domains: dict[str, set]) -> list[str]:
    """Format authoritative Jan-2012 domain values for markdown output."""
    lines: list[str] = []

    for column, values in reference_domains.items():
        sorted_values = sorted(str(value) for value in values)

        lines.append(f"### `{column}`")
        lines.append("")
        lines.append(f"- Distinct authoritative values: **{len(sorted_values):,}**")
        lines.append("")
        lines.extend(f"- `{value}`" for value in sorted_values)
        lines.append("")

    return lines


def write_profiling_report(
    report_path: str | Path,
    summary: dict[str, int],
    raw_profile: pd.DataFrame,
    cleaned_profile: pd.DataFrame,
    quarantine_reason_counts: pd.DataFrame,
    reference_domains: dict[str, set],
    used_raw_files: list[str],
) -> None:
    """
    Write a reproducible markdown profiling report based on the pipeline results.

    The report focuses on:
    - source and schema behaviour,
    - Jan-2012 authoritative reference domains,
    - validation and quarantine behaviour,
    - major engineering assumptions,
    - end-to-end record reconciliation.
    """
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []

    lines.append("# HDB Resale Flat Data Profiling Report")
    lines.append("")
    lines.append(
        "This report is generated programmatically from the ETL pipeline output "
        "so that the documented statistics remain consistent with the produced datasets."
    )
    lines.append("")

    # ------------------------------------------------------------------
    # 1. Pipeline summary
    # ------------------------------------------------------------------
    lines.append("## 1. Pipeline Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|---|---:|")

    for key, value in summary.items():
        display_name = key.replace("_", " ").title()
        lines.append(f"| {display_name} | {value:,} |")

    lines.append("")

    in_scope = summary.get("in_scope_rows", 0)
    cleaned = summary.get("cleaned_rows", 0)
    quarantined = summary.get("quarantined_rows", 0)

    if in_scope:
        cleaned_pct = cleaned / in_scope * 100
        quarantine_pct = quarantined / in_scope * 100

        lines.append(
            f"- **Cleaned pass rate:** {cleaned_pct:.2f}% "
            f"({cleaned:,} of {in_scope:,} in-scope rows)"
        )
        lines.append(
            f"- **Quarantine rate:** {quarantine_pct:.2f}% "
            f"({quarantined:,} of {in_scope:,} in-scope rows)"
        )

    lines.append("")

    # ------------------------------------------------------------------
    # 2. Source files / date semantics
    # ------------------------------------------------------------------
    lines.append("## 2. Source Files and Date Semantics")
    lines.append("")
    lines.append("The assessment-period records are sourced from the following raw files:")
    lines.append("")

    for file_name in used_raw_files:
        lines.append(f"- `{file_name}`")

    lines.append("")
    lines.append(
        "**Important source semantic change:** Jan-Feb 2012 records originate from "
        "the approval-date dataset, while Mar 2012 onward originates from "
        "registration-date datasets. The pipeline preserves these source semantics "
        "through lineage metadata (`_source_file` and `_date_basis`) and does not "
        "attempt to convert one date definition into the other because no reliable "
        "mapping is supplied."
    )
    lines.append("")

    # ------------------------------------------------------------------
    # 3. Raw profile
    # ------------------------------------------------------------------
    lines.append("## 3. Raw / In-Scope Dataset Profile")
    lines.append("")
    lines.append(raw_profile.to_markdown(index=False))
    lines.append("")

    lines.append(
        "**Schema evolution note:** `remaining_lease` is not present in all source "
        "files and changes representation in later datasets. Missing values in this "
        "column therefore reflect source-schema evolution rather than necessarily "
        "representing defective records."
    )
    lines.append("")

    # ------------------------------------------------------------------
    # 4. Jan-2012 authority
    # ------------------------------------------------------------------
    lines.append("## 4. January 2012 Authoritative Domains")
    lines.append("")
    lines.append(
        "January 2012 is treated as the **strict authoritative reference set** "
        "for `town`, `flat_type`, `flat_model`, and `storey_range`. "
        "The valid domains are derived dynamically from the Jan-2012 records rather "
        "than being hardcoded."
    )
    lines.append("")
    lines.append(
        "Any later record containing a value outside the corresponding Jan-2012 "
        "domain is quarantined, even where that value may represent legitimate "
        "business-domain evolution in subsequent years. This is an intentional "
        "implementation of the assessment requirement."
    )
    lines.append("")

    lines.extend(_format_reference_domains(reference_domains))

    # ------------------------------------------------------------------
    # 5. Quarantine analysis
    # ------------------------------------------------------------------
    lines.append("## 5. Quarantine Analysis")
    lines.append("")
    lines.append(
        "Rows that fail hard validation rules are retained in the quarantined output "
        "rather than silently deleted. This preserves traceability and enables "
        "investigation or replay."
    )
    lines.append("")

    if quarantine_reason_counts.empty:
        lines.append("No quarantine validation failures were recorded.")
    else:
        lines.append(quarantine_reason_counts.to_markdown(index=False))

    lines.append("")
    lines.append(
        "**Interpretation caveat:** Some quarantined values—particularly later "
        "`flat_model` and `storey_range` values—may be legitimate categories introduced "
        "after Jan 2012. They are still quarantined because Jan 2012 is required to be "
        "the strict authoritative domain."
    )
    lines.append("")

    # ------------------------------------------------------------------
    # 6. Cleaned profile
    # ------------------------------------------------------------------
    lines.append("## 6. Cleaned Dataset Profile")
    lines.append("")
    lines.append(cleaned_profile.to_markdown(index=False))
    lines.append("")

    # ------------------------------------------------------------------
    # 7. Engineering assumptions / decisions
    # ------------------------------------------------------------------
    lines.append("## 7. Key Assumptions and Engineering Decisions")
    lines.append("")

    lines.append("### 7.1 Approval date vs registration date")
    lines.append("")
    lines.append(
        "The meaning of the source `month` field changes at the source-system boundary. "
        "The pipeline preserves the supplied values and records the date basis in lineage "
        "metadata instead of attempting an unsupported reconciliation."
    )
    lines.append("")

    lines.append("### 7.2 Remaining lease")
    lines.append("")
    lines.append(
        "The source `remaining_lease` field is not treated as the authoritative result "
        "because it is absent from earlier files and changes representation later. "
        "The pipeline derives remaining lease independently from `lease_commence_date` "
        "using the assessment reference date of 1 Jan 2027 and a 99-year lease."
    )
    lines.append("")

    lines.append("### 7.3 Lease commencement date assumption")
    lines.append("")
    lines.append(
        "Only the lease commencement year is available. The pipeline therefore assumes "
        "1 January of that year as the lease commencement date. This is documented "
        "explicitly because month/day precision cannot be recovered from the source."
    )
    lines.append("")

    lines.append("### 7.4 Duplicate handling")
    lines.append("")
    lines.append(
        "Potential duplicate records are not silently removed. Duplicate handling is "
        "implemented as an auditable validation decision so that all source rows remain "
        "accounted for in either the cleaned or quarantined output."
    )
    lines.append("")

    lines.append("### 7.5 Resale price anomalies")
    lines.append("")
    lines.append(
        "Statistical resale-price anomalies are flagged rather than automatically "
        "quarantined because an unusual transaction may still be valid. The anomaly "
        "indicator is therefore a review signal, not an assertion of invalidity."
    )
    lines.append("")

    lines.append("### 7.6 Identifier collision handling")
    lines.append("")
    lines.append(
        "The prescribed base Resale Identifier can collide because it compresses several "
        "attributes. Collisions are resolved deterministically so that every transformed "
        "record receives a unique identifier without dropping source records."
    )
    lines.append("")

    lines.append("### 7.7 Identifier de-identification")
    lines.append("")
    lines.append(
        "The final identifier is de-identified using keyed HMAC-SHA256 rather than plain "
        "SHA-256. The secret is supplied externally through an environment variable or "
        "runtime parameter and is not committed to source control. This reduces exposure "
        "to dictionary attacks against predictable identifier values."
    )
    lines.append("")

    # ------------------------------------------------------------------
    # 8. Reconciliation
    # ------------------------------------------------------------------
    lines.append("## 8. Record Reconciliation")
    lines.append("")

    lines.append(
        f"- In-scope rows: **{in_scope:,}**"
    )
    lines.append(
        f"- Cleaned rows: **{cleaned:,}**"
    )
    lines.append(
        f"- Quarantined rows: **{quarantined:,}**"
    )
    lines.append("")

    if cleaned + quarantined == in_scope:
        lines.append(
            f"**Reconciliation passed:** {cleaned:,} cleaned + "
            f"{quarantined:,} quarantined = {in_scope:,} in-scope records."
        )
    else:
        lines.append(
            "**Reconciliation warning:** cleaned + quarantined does not equal "
            "the in-scope input count."
        )

    lines.append("")
    lines.append(
        "No in-scope source record should disappear silently during validation or "
        "transformation."
    )
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
