from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session(api_key: str | None = None) -> requests.Session:
    """Create a retry-enabled HTTP session suitable for public data APIs."""
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    if api_key:
        session.headers.update({"x-api-key": api_key})
    return session


def get_collection_metadata(collection_id: int, metadata_url: str, session: requests.Session | None = None) -> dict[str, Any]:
    """Fetch collection metadata and child dataset IDs from data.gov.sg."""
    session = session or build_session()
    response = session.get(metadata_url.format(collection_id=collection_id), timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Collection metadata request failed: {payload}")
    return payload["data"]["collectionMetadata"]


def get_dataset_metadata(dataset_id: str, metadata_url: str, session: requests.Session | None = None) -> dict[str, Any]:
    """Fetch metadata for a child dataset."""
    session = session or build_session()
    response = session.get(metadata_url.format(dataset_id=dataset_id), timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Dataset metadata request failed for {dataset_id}: {payload}")
    return payload["data"]


def _month_from_iso(value: str | None) -> pd.Period | None:
    if not value:
        return None
    return pd.Timestamp(value).to_period("M")


def discover_overlapping_datasets(
    collection_metadata: dict[str, Any],
    dataset_metadata_url: str,
    start_month: str,
    end_month: str,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Return collection child datasets whose metadata coverage overlaps the requested period."""
    session = session or build_session()
    target_start = pd.Period(start_month, freq="M")
    target_end = pd.Period(end_month, freq="M")
    selected: list[dict[str, Any]] = []
    for dataset_id in collection_metadata.get("childDatasets", []):
        metadata = get_dataset_metadata(dataset_id, dataset_metadata_url, session=session)
        coverage_start = _month_from_iso(metadata.get("coverageStart"))
        coverage_end = _month_from_iso(metadata.get("coverageEnd"))
        if coverage_start is None or coverage_end is None:
            continue
        if coverage_start <= target_end and coverage_end >= target_start:
            selected.append(metadata)
    return selected


def infer_date_basis(dataset_name: str) -> str:
    """Preserve the published transaction-date semantics as lineage metadata."""
    name = dataset_name.lower()
    if "approval date" in name:
        return "approval_date"
    if "registration date" in name:
        return "registration_date"
    return "unknown"


def download_dataset(
    dataset_id: str,
    initiate_download_url: str,
    poll_download_url: str,
    destination: Path,
    session: requests.Session | None = None,
    poll_attempts: int = 4,
    poll_interval_seconds: int = 15,
) -> Path:
    """Download a complete CSV using data.gov.sg's initiate-then-poll workflow."""
    session = session or build_session()
    initiate = session.get(initiate_download_url.format(dataset_id=dataset_id), timeout=60)
    initiate.raise_for_status()
    initiate_payload = initiate.json()
    if initiate_payload.get("code") != 0:
        raise RuntimeError(f"Initiate-download failed for {dataset_id}: {initiate_payload}")

    download_url = None
    last_payload: dict[str, Any] | None = None
    for attempt in range(poll_attempts):
        response = session.get(poll_download_url.format(dataset_id=dataset_id), timeout=60)
        response.raise_for_status()
        last_payload = response.json()
        if last_payload.get("code") == 0:
            download_url = last_payload.get("data", {}).get("url")
            if download_url:
                break
        if attempt < poll_attempts - 1:
            time.sleep(poll_interval_seconds)
    if not download_url:
        raise RuntimeError(f"No download URL returned for {dataset_id}: {last_payload}")

    with session.get(download_url, stream=True, timeout=120) as stream:
        stream.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            for chunk in stream.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return destination


def download_collection_sources(
    collection_id: int,
    metadata_url: str,
    dataset_metadata_url: str,
    initiate_download_url: str,
    poll_download_url: str,
    raw_dir: str | Path,
    start_month: str,
    end_month: str,
    api_key: str | None = None,
) -> list[Path]:
    """Discover overlapping child datasets from Collection 189 and download them unchanged."""
    session = build_session(api_key=api_key)
    collection = get_collection_metadata(collection_id, metadata_url, session=session)
    datasets = discover_overlapping_datasets(
        collection, dataset_metadata_url, start_month, end_month, session=session
    )
    raw_dir = Path(raw_dir)
    outputs: list[Path] = []
    for metadata in datasets:
        name = metadata["name"]
        dataset_id = metadata["datasetId"]
        destination = raw_dir / f"{name}.csv"
        outputs.append(
            download_dataset(
                dataset_id, initiate_download_url, poll_download_url, destination, session=session
            )
        )
    return outputs


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_local_csv_period(path: str | Path) -> tuple[pd.Period, pd.Period]:
    """Read only the month column and return its min/max month."""
    months = pd.read_csv(path, usecols=["month"], dtype={"month": "string"})["month"]
    periods = pd.PeriodIndex(months, freq="M")
    return periods.min(), periods.max()


def copy_local_overlapping_sources(
    source_paths: Iterable[str | Path],
    raw_dir: str | Path,
    start_month: str,
    end_month: str,
) -> list[Path]:
    """Copy only source files that overlap the assessment window; bytes remain unchanged."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    target_start = pd.Period(start_month, freq="M")
    target_end = pd.Period(end_month, freq="M")
    copied: list[Path] = []
    for source in map(Path, source_paths):
        source_start, source_end = inspect_local_csv_period(source)
        if source_start <= target_end and source_end >= target_start:
            destination = raw_dir / source.name
            shutil.copyfile(source, destination)
            if file_sha256(source) != file_sha256(destination):
                raise IOError(f"Raw copy checksum mismatch: {source.name}")
            copied.append(destination)
    return copied


def deterministic_run_id(paths: Iterable[str | Path]) -> str:
    """Create a deterministic run ID from source file hashes to support idempotent outputs."""
    items = sorted((Path(p).name, file_sha256(p)) for p in paths)
    payload = "|".join(f"{name}:{digest}" for name, digest in items)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
