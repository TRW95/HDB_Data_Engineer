# HDB Resale Flat Data Profiling Report

This report is generated programmatically from the ETL pipeline output so that the documented statistics remain consistent with the produced datasets.

## 1. Pipeline Summary

| Metric | Count |
|---|---:|
| Raw Rows Across Selected Files | 701,039 |
| In Scope Rows | 113,053 |
| Cleaned Rows | 104,783 |
| Quarantined Rows | 8,270 |
| Transformed Rows | 104,783 |
| Hashed Rows | 104,783 |
| Price Anomaly Rows | 2,110 |

- **Cleaned pass rate:** 92.68% (104,783 of 113,053 in-scope rows)
- **Quarantine rate:** 7.32% (8,270 of 113,053 in-scope rows)

## 2. Source Files and Date Semantics

The assessment-period records are sourced from the following raw files:

- `Resale Flat Prices (Based on Approval Date), 2000 - Feb 2012.csv`
- `Resale Flat Prices (Based on Registration Date), From Jan 2015 to Dec 2016.csv`
- `Resale Flat Prices (Based on Registration Date), From Mar 2012 to Dec 2014.csv`
- `Resale flat prices based on registration date from Jan-2017 onwards.csv`

**Important source semantic change:** Jan-Feb 2012 records originate from the approval-date dataset, while Mar 2012 onward originates from registration-date datasets. The pipeline preserves these source semantics through lineage metadata (`_source_file` and `_date_basis`) and does not attempt to convert one date definition into the other because no reliable mapping is supplied.

## 3. Raw / In-Scope Dataset Profile

| column              | dtype   |   rows |   null_count |   null_pct |   distinct_count |    min |           max |       mean |   median |
|:--------------------|:--------|-------:|-------------:|-----------:|-----------------:|-------:|--------------:|-----------:|---------:|
| month               | object  | 113053 |            0 |      0     |               72 |    nan |    nan        |    nan     |      nan |
| town                | object  | 113053 |            0 |      0     |               26 |    nan |    nan        |    nan     |      nan |
| flat_type           | object  | 113053 |            0 |      0     |                7 |    nan |    nan        |    nan     |      nan |
| block               | object  | 113053 |            0 |      0     |             2193 |    nan |    nan        |    nan     |      nan |
| street_name         | object  | 113053 |            0 |      0     |              526 |    nan |    nan        |    nan     |      nan |
| storey_range        | object  | 113053 |            0 |      0     |               25 |    nan |    nan        |    nan     |      nan |
| floor_area_sqm      | float64 | 113053 |            0 |      0     |              169 |     31 |    280        |     96.784 |       96 |
| flat_model          | object  | 113053 |            0 |      0     |               20 |    nan |    nan        |    nan     |      nan |
| lease_commence_date | int64   | 113053 |            0 |      0     |               50 |   1966 |   2015        |   1990.55  |     1988 |
| resale_price        | float64 | 113053 |            0 |      0     |             2865 | 175000 |      1.18e+06 | 449660     |   425000 |
| _source_file        | object  | 113053 |            0 |      0     |                4 |    nan |    nan        |    nan     |      nan |
| _source_row_number  | int64   | 113053 |            0 |      0     |            55391 |      2 | 369652        |  30398.1   |    18844 |
| _date_basis         | object  | 113053 |            0 |      0     |                2 |    nan |    nan        |    nan     |      nan |
| _pipeline_run_id    | object  | 113053 |            0 |      0     |                1 |    nan |    nan        |    nan     |      nan |
| remaining_lease     | object  | 113053 |        55391 |     48.996 |              631 |    nan |    nan        |    nan     |      nan |

**Schema evolution note:** `remaining_lease` is not present in all source files and changes representation in later datasets. Missing values in this column therefore reflect source-schema evolution rather than necessarily representing defective records.

## 4. January 2012 Authoritative Domains

January 2012 is treated as the **strict authoritative reference set** for `town`, `flat_type`, `flat_model`, and `storey_range`. The valid domains are derived dynamically from the Jan-2012 records rather than being hardcoded.

Any later record containing a value outside the corresponding Jan-2012 domain is quarantined, even where that value may represent legitimate business-domain evolution in subsequent years. This is an intentional implementation of the assessment requirement.

### `town`

- Distinct authoritative values: **26**

- `ANG MO KIO`
- `BEDOK`
- `BISHAN`
- `BUKIT BATOK`
- `BUKIT MERAH`
- `BUKIT PANJANG`
- `BUKIT TIMAH`
- `CENTRAL AREA`
- `CHOA CHU KANG`
- `CLEMENTI`
- `GEYLANG`
- `HOUGANG`
- `JURONG EAST`
- `JURONG WEST`
- `KALLANG/WHAMPOA`
- `MARINE PARADE`
- `PASIR RIS`
- `PUNGGOL`
- `QUEENSTOWN`
- `SEMBAWANG`
- `SENGKANG`
- `SERANGOON`
- `TAMPINES`
- `TOA PAYOH`
- `WOODLANDS`
- `YISHUN`

### `flat_type`

- Distinct authoritative values: **7**

- `1 ROOM`
- `2 ROOM`
- `3 ROOM`
- `4 ROOM`
- `5 ROOM`
- `EXECUTIVE`
- `MULTI-GENERATION`

### `flat_model`

- Distinct authoritative values: **13**

- `Adjoined flat`
- `Apartment`
- `Improved`
- `Maisonette`
- `Model A`
- `Model A-Maisonette`
- `Model A2`
- `Multi Generation`
- `New Generation`
- `Premium Apartment`
- `Simplified`
- `Standard`
- `Terrace`

### `storey_range`

- Distinct authoritative values: **12**

- `01 TO 03`
- `04 TO 06`
- `07 TO 09`
- `10 TO 12`
- `13 TO 15`
- `16 TO 18`
- `19 TO 21`
- `22 TO 24`
- `25 TO 27`
- `28 TO 30`
- `31 TO 33`
- `34 TO 36`

## 5. Quarantine Analysis

Rows that fail hard validation rules are retained in the quarantined output rather than silently deleted. This preserves traceability and enables investigation or replay.

| validation_rule      |   row_count |
|:---------------------|------------:|
| INVALID_STOREY_RANGE |        7050 |
| INVALID_FLAT_MODEL   |         870 |
| DUPLICATE_RECORD     |         451 |

**Interpretation caveat:** Some quarantined values—particularly later `flat_model` and `storey_range` values—may be legitimate categories introduced after Jan 2012. They are still quarantined because Jan 2012 is required to be the strict authoritative domain.

## 6. Cleaned Dataset Profile

| column                      | dtype   |   rows |   null_count |   null_pct |   distinct_count |    min |              max |       mean |   median |
|:----------------------------|:--------|-------:|-------------:|-----------:|-----------------:|-------:|-----------------:|-----------:|---------:|
| month                       | object  | 104783 |            0 |      0     |               69 |    nan |    nan           |    nan     |      nan |
| town                        | object  | 104783 |            0 |      0     |               26 |    nan |    nan           |    nan     |      nan |
| flat_type                   | object  | 104783 |            0 |      0     |                7 |    nan |    nan           |    nan     |      nan |
| block                       | object  | 104783 |            0 |      0     |             2170 |    nan |    nan           |    nan     |      nan |
| street_name                 | object  | 104783 |            0 |      0     |              522 |    nan |    nan           |    nan     |      nan |
| storey_range                | object  | 104783 |            0 |      0     |               12 |    nan |    nan           |    nan     |      nan |
| floor_area_sqm              | float64 | 104783 |            0 |      0     |              167 |     31 |    280           |     96.712 |       95 |
| flat_model                  | object  | 104783 |            0 |      0     |               13 |    nan |    nan           |    nan     |      nan |
| lease_commence_date         | int64   | 104783 |            0 |      0     |               50 |   1966 |   2015           |   1990.43  |     1988 |
| resale_price                | float64 | 104783 |            0 |      0     |             2707 | 175000 |      1.16e+06    | 446029     |   422000 |
| _source_file                | object  | 104783 |            0 |      0     |                4 |    nan |    nan           |    nan     |      nan |
| _source_row_number          | int64   | 104783 |            0 |      0     |            55075 |      2 | 369652           |  32276.6   |    20014 |
| _date_basis                 | object  | 104783 |            0 |      0     |                2 |    nan |    nan           |    nan     |      nan |
| _pipeline_run_id            | object  | 104783 |            0 |      0     |                1 |    nan |    nan           |    nan     |      nan |
| remaining_lease             | object  | 104783 |        48189 |     45.989 |              629 |    nan |    nan           |    nan     |      nan |
| validation_errors           | object  | 104783 |            0 |      0     |                1 |    nan |    nan           |    nan     |      nan |
| validation_status           | object  | 104783 |            0 |      0     |                1 |    nan |    nan           |    nan     |      nan |
| remaining_lease_years_2027  | Int64   | 104783 |            0 |      0     |               50 |     38 |     87           |     62.426 |       60 |
| remaining_lease_months_2027 | Int64   | 104783 |            0 |      0     |                1 |      0 |      0           |      0     |        0 |
| remaining_lease_as_of_2027  | string  | 104783 |            0 |      0     |               50 |    nan |    nan           |    nan     |      nan |
| year                        | int32   | 104783 |            0 |      0     |                6 |   2012 |   2017           |   2014.64  |     2015 |
| group_size                  | int64   | 104783 |            0 |      0     |              321 |      1 |    769           |    312.659 |      285 |
| q1                          | float64 | 104783 |            0 |      0     |              448 | 188000 | 980000           | 410328     |   395000 |
| q3                          | float64 | 104783 |            0 |      0     |              489 | 188000 | 982500           | 475965     |   450000 |
| iqr                         | float64 | 104783 |            0 |      0     |              389 |      0 | 236500           |  65636.6   |    53000 |
| price_lower_bound           | float64 | 104783 |            0 |      0     |              557 |  45250 | 980000           | 311873     |   293000 |
| price_upper_bound           | float64 | 104783 |            0 |      0     |              608 | 188000 |      1.17325e+06 | 574420     |   540188 |
| resale_price_anomaly_flag   | bool    | 104783 |            0 |      0     |                2 |      0 |      1           |      0.02  |        0 |
| resale_price_anomaly_reason | object  | 104783 |            0 |      0     |                4 |    nan |    nan           |    nan     |      nan |

## 7. Key Assumptions and Engineering Decisions

### 7.1 Approval date vs registration date

The meaning of the source `month` field changes at the source-system boundary. The pipeline preserves the supplied values and records the date basis in lineage metadata instead of attempting an unsupported reconciliation.

### 7.2 Remaining lease

The source `remaining_lease` field is not treated as the authoritative result because it is absent from earlier files and changes representation later. The pipeline derives remaining lease independently from `lease_commence_date` using the assessment reference date of 1 Jan 2027 and a 99-year lease.

### 7.3 Lease commencement date assumption

Only the lease commencement year is available. The pipeline therefore assumes 1 January of that year as the lease commencement date. This is documented explicitly because month/day precision cannot be recovered from the source.

### 7.4 Duplicate handling

Potential duplicate records are not silently removed. Duplicate handling is implemented as an auditable validation decision so that all source rows remain accounted for in either the cleaned or quarantined output.

### 7.5 Resale price anomalies

Statistical resale-price anomalies are flagged rather than automatically quarantined because an unusual transaction may still be valid. The anomaly indicator is therefore a review signal, not an assertion of invalidity.

### 7.6 Identifier collision handling

The prescribed base Resale Identifier can collide because it compresses several attributes. Collisions are resolved deterministically so that every transformed record receives a unique identifier without dropping source records.

### 7.7 Identifier de-identification

The final identifier is de-identified using keyed HMAC-SHA256 rather than plain SHA-256. The secret is supplied externally through an environment variable or runtime parameter and is not committed to source control. This reduces exposure to dictionary attacks against predictable identifier values.

## 8. Record Reconciliation

- In-scope rows: **113,053**
- Cleaned rows: **104,783**
- Quarantined rows: **8,270**

**Reconciliation passed:** 104,783 cleaned + 8,270 quarantined = 113,053 in-scope records.

No in-scope source record should disappear silently during validation or transformation.
