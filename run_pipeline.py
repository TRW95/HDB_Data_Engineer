"""Entry point for the HDB Part 1 ETL pipeline."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from hdb_etl.pipeline import run_pipeline

if __name__ == "__main__":
    result = run_pipeline(ROOT, write_outputs=True)
    for key, value in result["summary"].items():
        print(f"{key}: {value:,}" if isinstance(value, int) else f"{key}: {value}")
