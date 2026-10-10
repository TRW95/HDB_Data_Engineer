# HDB Senior Data Engineer Technical Assessment — Part 1

This repository implements the Part 1 ETL pipeline for HDB resale flat transactions from **January 2012 to December 2017**. 

## 1. Submission contents

- `notebooks/hdb_resale_etl.ipynb` — executable walkthrough with markdown explanations, inline comments, and saved cell outputs.
- `src/hdb_etl/` — reusable Python extraction, profiling, validation, transformation, and pipeline logic.
- `data/raw/` — source CSV files preserved byte-for-byte as received.
- `data/cleaned/hdb_resale_cleaned.csv` — rows that pass hard data-quality rules, with derived lease and anomaly flags.
- `data/transformed/hdb_resale_transformed.csv` — cleaned rows after Resale Identifier generation and deterministic collision handling.
- `data/quarantined/hdb_resale_quarantined.csv` — rows failing one or more hard validation rules, including candidate duplicates.
- `data/hashed/hdb_resale_hashed.csv` — transformed valid rows with the clear-text identifier removed and replaced by an HMAC-SHA256 identifier.
- `reports/data_profiling_report.md` — profiling observations across the pipeline lifecycle, including quarantine analysis.
- `tests/` — focused unit tests for validation, lease calculation, identifier collision handling, and hashing.

## 2. Source extraction

The source collection is data.gov.sg **Collection 189 — Resale Flat Prices**. `src/hdb_etl/extract.py` supports:

1. fetching collection metadata;
2. discovering child datasets whose metadata coverage overlaps Jan 2012–Dec 2017;
3. downloading the source CSVs programmatically; and
4. preserving the downloaded files unchanged under `data/raw/`.

The supplied repository already contains the relevant raw input files so the notebook and pipeline can be reviewed and executed without a network call.

The data source changes transaction-date semantics at March 2012:

- Jan–Feb 2012 records are based on **resale approval date**;
- Mar 2012 onward records are based on **registration date**.

The pipeline retains `_date_basis` and `_source_file` as lineage metadata and does not attempt to reconcile the two event definitions.

## 3. Key engineering decisions and assumptions

### Jan 2012 as the strict authoritative set

The allowed domains for `town`, `flat_type`, `flat_model`, and `storey_range` are derived dynamically from the Jan 2012 records. Later values that were not observed in Jan 2012 are quarantined.

This deliberately means that some quarantined rows may represent later domain evolution rather than obvious source corruption. 

### Approval date vs registration date

The `month` column is retained exactly as supplied.

- Jan–Feb 2012 represents approval month.
- Mar 2012 onward represents registration month.

`_date_basis` and `_source_file` are retained so this semantic break is traceable.

### Schema evolution and `remaining_lease`

`remaining_lease` is absent from the earlier files and appears in different representations later. It is preserved as a source field where present but is **not** used as the assessment calculation.

Missing historical values are treated as schema evolution, not automatically as defective records.

### Remaining lease as at 1 Jan 2027

The source provides `lease_commence_date` only as a year. The pipeline therefore assumes lease commencement on **1 January of the stated year**, applies a 99-year lease, and calculates whole years/months remaining at 1 Jan 2027.

This assumption is explicit because month/day precision is not available in the supplied source.

### Hard failures vs anomaly flags

Invalid authoritative-domain values, missing required values, impossible numeric values, invalid months, and subsequent exact duplicate candidates are quarantined.

A statistically unusual resale price is **not** automatically invalid; it remains in the cleaned dataset and receives an anomaly flag.

### Duplicate candidates

Because no transaction identifier exists in the source, candidate duplicates are defined as subsequent exact matches across the stable transaction attributes:

`month`, `town`, `flat_type`, `block`, `street_name`, `storey_range`, `floor_area_sqm`, `flat_model`, `lease_commence_date`, `resale_price`.

The first occurrence stays in the accepted path and later occurrences are quarantined as `DUPLICATE_RECORD`.


### Price anomaly heuristic

The pipeline uses a transparent grouped-IQR heuristic within `year + town + flat_type` cohorts, with a minimum group size of 20.

Values outside:

```text
Q1 - 1.5 × IQR
Q3 + 1.5 × IQR
```

are flagged.

Small cohorts are not labelled anomalous because there is insufficient comparison data.

### Resale Identifier collision handling

The required base identifier is generated from the prescribed components.

Because this compressed key is naturally non-unique, collision groups receive deterministic `-001`, `-002`, ... suffixes ordered by source file and source row number.

Non-collision identifiers remain unchanged. No valid record is dropped.

### De-identification

The final identifier is protected using **HMAC-SHA256**, not plain SHA-256.

HMAC requires a secret key, making offline dictionary generation materially harder for predictable structured identifiers. The clear-text identifier is removed from the hashed output.

The secret is supplied externally and must not be committed to Git.

### Idempotency and lineage

Transformations are deterministic.

A `_pipeline_run_id` is derived from raw file checksums rather than wall-clock time, so re-running unchanged inputs does not create different record-level metadata.

HMAC identifiers are deterministic when the same external secret is supplied.

`_source_file` and `_source_row_number` support row-level traceability.

---

# 4. Step-by-step: run the pipeline

The following steps reproduce the pipeline outputs from the raw input files.

## Step 1 — Open a terminal at the repository root

Run all commands from the project root — the folder containing:

```text
README.md
config.yaml
requirements.txt
run_pipeline.py
notebooks/
src/
tests/
data/
reports/
```

Example on Windows PowerShell:

```powershell
cd "C:\path\to\hdb_senior_data_engineer_submission"
```

Confirm the location:

```powershell
dir
```

## Step 2 — Create a Python virtual environment

Recommended Python version:

```text
Python 3.11+
```

Windows PowerShell:

```powershell
python -m venv .venv
```

Activate the virtual environment:

```powershell
.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution for the current session, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

After activation, the terminal prompt should begin with:

```text
(.venv)
```

For macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

## Step 3 — Install dependencies

Run:

```powershell
pip install -r requirements.txt
```

This installs the libraries required for:

- ETL execution;
- data profiling;
- markdown report generation;
- unit testing; and
- Jupyter Notebook execution.

## Step 4 — Set `PYTHONPATH`

The reusable Python package is stored under `src/`.

Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
```

macOS/Linux:

```bash
export PYTHONPATH=src
```

## Step 5 — Run the unit tests

Before running the full pipeline:

```powershell
pytest -q
```

Expected result:

```text
4 passed
```

The tests cover the main validation and transformation behaviours, including lease calculation, identifier handling, collision resolution, and hashing.

## Step 6 — Set the HMAC secret

The hashed output uses **HMAC-SHA256**.

The HMAC secret is intentionally not stored in the repository.

For a local assessment run, set a temporary secret in the current terminal session.

Windows PowerShell:

```powershell
$env:HDB_HASH_SECRET = "replace-with-a-local-test-secret"
```

macOS/Linux:

```bash
export HDB_HASH_SECRET="replace-with-a-local-test-secret"
```

The same secret produces the same pseudonymous identifiers on repeat runs.

If the secret is changed, the resulting HMAC identifiers will also change.

For a production implementation, the secret should be supplied through a managed secret store rather than source control.

## Step 7 — Optional: delete generated outputs before testing reproducibility

The raw files under:

```text
data/raw/
```

must remain unchanged.

To test that the pipeline can recreate all generated outputs, delete only the generated files.

Windows PowerShell:

```powershell
Remove-Item "data\cleaned\*" -Force
Remove-Item "data\transformed\*" -Force
Remove-Item "data\quarantined\*" -Force
Remove-Item "data\hashed\*" -Force
Remove-Item "reports\data_profiling_report.md" -Force
```

Do **not** delete:

```text
data/raw/
```

## Step 8 — Run the ETL pipeline

Run:

```powershell
python run_pipeline.py
```

The pipeline performs:

```text
Raw source CSVs
      │
      ▼
Read source files and attach lineage
      │
      ▼
Filter to Jan 2012–Dec 2017
      │
      ▼
Build Jan-2012 authoritative domains
      │
      ▼
Validate records
   ┌──┴─────────────┐
   ▼                ▼
Cleaned         Quarantined
   │
   ▼
Calculate remaining lease
   │
   ▼
Flag resale-price anomalies
   │
   ▼
Generate Resale Identifier
   │
   ▼
Resolve identifier collisions
   │
   ▼
Transformed
   │
   ▼
HMAC-SHA256 de-identification
   │
   ▼
Hashed
```

It also regenerates:

```text
reports/data_profiling_report.md
```

## Step 9 — Verify the pipeline summary

A successful run should produce approximately:

```text
raw_rows_across_selected_files: 701039
in_scope_rows: 113053
cleaned_rows: 104783
quarantined_rows: 8270
transformed_rows: 104783
hashed_rows: 104783
price_anomaly_rows: 2110
```

The most important reconciliation check is:

```text
104,783 cleaned
+ 8,270 quarantined
= 113,053 in-scope records
```

The pipeline also asserts:

```text
transformed rows = cleaned rows
hashed rows = cleaned rows
Resale Identifier is unique
hashed identifier is unique
```

If any assertion fails, the pipeline stops rather than silently writing inconsistent outputs.

## Step 10 — Verify the generated files

Run:

```powershell
dir data\cleaned
dir data\transformed
dir data\quarantined
dir data\hashed
dir reports
```

Expected generated files:

```text
data/cleaned/hdb_resale_cleaned.csv
data/transformed/hdb_resale_transformed.csv
data/quarantined/hdb_resale_quarantined.csv
data/hashed/hdb_resale_hashed.csv
reports/data_profiling_report.md
```

The raw source files remain under:

```text
data/raw/
```

## Step 11 — Optional manual row-count verification

Start Python:

```powershell
python
```

Then run:

```python
import pandas as pd

cleaned = pd.read_csv("data/cleaned/hdb_resale_cleaned.csv")
quarantined = pd.read_csv("data/quarantined/hdb_resale_quarantined.csv")
transformed = pd.read_csv("data/transformed/hdb_resale_transformed.csv")
hashed = pd.read_csv("data/hashed/hdb_resale_hashed.csv")

print("Cleaned:", len(cleaned))
print("Quarantined:", len(quarantined))
print("Transformed:", len(transformed))
print("Hashed:", len(hashed))
print("Reconciled:", len(cleaned) + len(quarantined))
```

Expected:

```text
Cleaned: 104783
Quarantined: 8270
Transformed: 104783
Hashed: 104783
Reconciled: 113053
```

Exit Python:

```python
exit()
```

## Step 12 — Optional identifier uniqueness verification

Run:

```powershell
python -c "import pandas as pd; t=pd.read_csv('data/transformed/hdb_resale_transformed.csv'); print('rows=',len(t)); print('unique_ids=',t['resale_identifier'].nunique()); print('duplicates=',t['resale_identifier'].duplicated().sum())"
```

Expected:

```text
rows= 104783
unique_ids= 104783
duplicates= 0
```

Verify the hashed identifier:

```powershell
python -c "import pandas as pd; h=pd.read_csv('data/hashed/hdb_resale_hashed.csv'); print('rows=',len(h)); print('unique_hashes=',h['hashed_resale_identifier'].nunique()); print('duplicates=',h['hashed_resale_identifier'].duplicated().sum())"
```

Expected:

```text
rows= 104783
unique_hashes= 104783
duplicates= 0
```

## Step 13 — Review the quarantine output

Open:

```text
data/quarantined/hdb_resale_quarantined.csv
```

Key fields include:

```text
validation_errors
_source_file
_source_row_number
_date_basis
_pipeline_run_id
```

The quarantine output retains failed records rather than silently removing them.

To inspect the most common validation failures:

```powershell
python -c "import pandas as pd; q=pd.read_csv('data/quarantined/hdb_resale_quarantined.csv'); print(q['validation_errors'].value_counts().head(20))"
```

Some later values may represent valid business-domain evolution but are still quarantined because the assessment requires Jan 2012 to be treated as the strict authoritative set.

## Step 14 — Review the generated profiling report

Open:

```text
reports/data_profiling_report.md
```

The report is generated programmatically from the same pipeline run and includes:

- pipeline row counts;
- source and schema behaviour;
- Jan-2012 authoritative domains;
- validation outcomes;
- quarantine analysis;
- cleaned-data profiling;
- engineering assumptions; and
- record reconciliation.

---

## 5. Run the Jupyter Notebook

The notebook provides the initial developement and may be used for walkthrough and already contains saved cell outputs.

From the repository root:

```powershell
jupyter notebook notebooks/hdb_resale_etl.ipynb
```

Alternatively:

```powershell
jupyter notebook
```

and open:

```text
notebooks/hdb_resale_etl.ipynb
```

To fully verify it, restart the kernel and run all cells.

The notebook uses an ephemeral in-memory HMAC key for its demonstration run and does not print or persist the secret.

---

## 6. Optional: re-download source data from data.gov.sg

The raw files are already supplied for reproducibility, so this step is not required for normal review.

The extraction module can also discover/download the source datasets programmatically.

Example:

```python
from pathlib import Path
import os

from hdb_etl.config import load_config
from hdb_etl.extract import download_collection_sources

cfg = load_config("config.yaml")
collection = cfg["collection"]
pipeline = cfg["pipeline"]

download_collection_sources(
    collection_id=collection["id"],
    metadata_url=collection["metadata_url"],
    dataset_metadata_url=collection["dataset_metadata_url"],
    initiate_download_url=collection["initiate_download_url"],
    poll_download_url=collection["poll_download_url"],
    raw_dir=Path(cfg["paths"]["raw"]),
    start_month=pipeline["start_month"],
    end_month=pipeline["end_month"],
    api_key=os.environ.get("DATA_GOV_SG_API_KEY"),
)
```

A data.gov.sg API key can be supplied through `DATA_GOV_SG_API_KEY` where required.

---

## 7. Output contract

The five mandatory output groups are produced as follows:

| Group | Location | Contract |
|---|---|---|
| Raw | `data/raw/` | Source files preserved unchanged |
| Cleaned | `data/cleaned/hdb_resale_cleaned.csv` | Passed hard validation; includes lease derivation and price-anomaly flags |
| Transformed | `data/transformed/hdb_resale_transformed.csv` | Cleaned rows plus required Resale Identifier and collision metadata |
| Quarantined | `data/quarantined/hdb_resale_quarantined.csv` | Failed rows retained with validation reasons and lineage |
| Hashed | `data/hashed/hdb_resale_hashed.csv` | Valid transformed rows with keyed HMAC identifier and without clear-text identifier |

A core reconciliation assertion ensures:

```text
in-scope input rows = cleaned rows + quarantined rows
```

Transformation and hashing stages must preserve the cleaned row count.

---

## 8. Repository structure

```text
.
├── README.md
├── config.yaml
├── requirements.txt
├── run_pipeline.py
├── notebooks/
│   └── hdb_resale_etl.ipynb
├── src/
│   └── hdb_etl/
│       ├── __init__.py
│       ├── config.py
│       ├── extract.py
│       ├── profile.py
│       ├── validate.py
│       ├── transform.py
│       └── pipeline.py
├── tests/
├── data/
│   ├── raw/
│   ├── cleaned/
│   ├── transformed/
│   ├── quarantined/
│   └── hashed/
├── reports/
│   └── data_profiling_report.md
└── architecture/
```

`architecture/` is reserved for the Part 2 PNG architecture diagrams.
