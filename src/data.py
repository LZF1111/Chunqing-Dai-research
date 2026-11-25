"""Data contract, validation and split helpers for the P0 benchmark."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


LABEL_COLUMN = "aeronet_aod_500"
BASELINE_COLUMN = "satellite_aod"
CATEGORICAL_FEATURES = ["surface_type"]
NUMERIC_FEATURES = [
    "latitude",
    "longitude",
    "satellite_aod",
    "qa_value",
    "solar_zenith_deg",
    "view_zenith_deg",
    "relative_azimuth_deg",
    "air_temperature_k",
    "relative_humidity_pct",
    "boundary_layer_height_m",
]
OPTIONAL_NUMERIC_COLUMNS = [
    "air_temperature_k",
    "relative_humidity_pct",
    "boundary_layer_height_m",
]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES
REQUIRED_COLUMNS = [
    "station_id",
    "timestamp",
    "latitude",
    "longitude",
    LABEL_COLUMN,
    BASELINE_COLUMN,
    "qa_value",
    "solar_zenith_deg",
    "view_zenith_deg",
    "relative_azimuth_deg",
    "surface_type",
]

NUMERIC_COLUMNS = [
    "latitude",
    "longitude",
    LABEL_COLUMN,
    BASELINE_COLUMN,
    "qa_value",
    "solar_zenith_deg",
    "view_zenith_deg",
    "relative_azimuth_deg",
    "air_temperature_k",
    "relative_humidity_pct",
    "boundary_layer_height_m",
]

RANGES = {
    "latitude": (-90.0, 90.0),
    "longitude": (-180.0, 180.0),
    LABEL_COLUMN: (0.0, None),
    BASELINE_COLUMN: (0.0, None),
    "qa_value": (0.0, 1.0),
    "solar_zenith_deg": (0.0, 180.0),
    "view_zenith_deg": (0.0, 180.0),
    "relative_azimuth_deg": (0.0, 360.0),
    "air_temperature_k": (150.0, 350.0),
    "relative_humidity_pct": (0.0, 100.0),
    "boundary_layer_height_m": (0.0, None),
}


class DataContractError(ValueError):
    """Raised when an input file cannot satisfy the P0 data contract."""


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _append_reason(reasons: pd.Series, mask: pd.Series, message: str) -> None:
    empty = reasons == ""
    mask_series = pd.Series(mask, index=reasons.index)
    reasons.loc[mask_series & empty] = message


def validate_collocations(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate rows and return accepted and rejected frames.

    Rejection is row-level so that a real data preparation run can audit the
    quality filters without silently dropping observations.
    """

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise DataContractError(
            "Missing required columns: " + ", ".join(sorted(missing))
        )

    data = frame.copy()
    reasons = pd.Series("", index=data.index, dtype="string")

    data["station_id"] = data["station_id"].astype("string").str.strip()
    _append_reason(
        reasons,
        data["station_id"].isna() | (data["station_id"] == ""),
        "empty station_id",
    )

    data["surface_type"] = data["surface_type"].astype("string").str.strip()
    _append_reason(
        reasons,
        data["surface_type"].isna() | (data["surface_type"] == ""),
        "empty surface_type",
    )

    timestamps = pd.to_datetime(data["timestamp"], errors="coerce", utc=True)
    _append_reason(reasons, timestamps.isna(), "invalid timestamp")
    data["timestamp"] = timestamps
    _append_reason(
        reasons,
        data.duplicated(subset=["station_id", "timestamp"], keep=False),
        "duplicate station_id and timestamp",
    )

    for column in NUMERIC_COLUMNS:
        optional = column in OPTIONAL_NUMERIC_COLUMNS
        if column not in data.columns:
            data[column] = np.nan
        raw_values = data[column]
        data[column] = pd.to_numeric(raw_values, errors="coerce")
        non_empty = raw_values.notna() & raw_values.astype("string").str.strip().ne("")
        non_empty = non_empty.fillna(False)
        invalid = data[column].isna() if not optional else data[column].isna() & non_empty
        _append_reason(reasons, invalid, f"invalid {column}")
        _append_reason(
            reasons,
            data[column].notna()
            & ~np.isfinite(data[column].to_numpy(dtype=float, na_value=np.nan)),
            f"non-finite {column}",
        )
        lower, upper = RANGES[column]
        values = data[column]
        if lower is not None:
            _append_reason(reasons, values < lower, f"{column} below lower bound")
        if upper is not None:
            _append_reason(reasons, values > upper, f"{column} above upper bound")

    rejected = data[reasons != ""].copy()
    rejected["rejection_reason"] = reasons[reasons != ""].astype(str)
    accepted = data[reasons == ""].copy()
    accepted["timestamp"] = accepted["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    rejected["timestamp"] = rejected["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return accepted.reset_index(drop=True), rejected.reset_index(drop=True)


def load_and_validate(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not path.exists():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    return validate_collocations(pd.read_csv(path))


def _require_years(years: Iterable[int], label: str) -> None:
    if not list(years):
        raise DataContractError(f"The {label} split has no rows")


def split_by_time(
    data: pd.DataFrame,
    validation_year: int | None = None,
    test_year: int | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    timestamps = pd.to_datetime(data["timestamp"], utc=True)
    years = sorted(timestamps.dt.year.unique().tolist())
    if len(years) < 3:
        raise DataContractError(
            "Time split needs at least three calendar years for train, validation and test"
        )
    selected_test = test_year if test_year is not None else years[-1]
    if selected_test not in years:
        raise DataContractError(f"test year {selected_test} is absent from the input")
    available_for_validation = [year for year in years if year < selected_test]
    if not available_for_validation:
        raise DataContractError(
            f"test year {selected_test} has no earlier year available for validation"
        )
    selected_validation = (
        validation_year
        if validation_year is not None
        else available_for_validation[-1]
    )
    if selected_validation not in years or selected_validation >= selected_test:
        raise DataContractError(
            f"validation year {selected_validation} must precede test year {selected_test}"
        )

    year_values = timestamps.dt.year
    masks = {
        "train": year_values < selected_validation,
        "validation": year_values == selected_validation,
        "test": year_values == selected_test,
    }
    splits = {
        name: data.loc[mask].reset_index(drop=True) for name, mask in masks.items()
    }
    for name, split in splits.items():
        _require_years(split.index, name)
    details = {
        "mode": "time",
        "train_years": sorted(
            pd.to_datetime(splits["train"]["timestamp"], utc=True).dt.year.unique().tolist()
        ),
        "validation_year": selected_validation,
        "test_year": selected_test,
    }
    return splits, details


def split_by_station(data: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    stations = sorted(data["station_id"].astype(str).unique().tolist())
    if len(stations) < 3:
        raise DataContractError("Station split needs at least three stations")
    holdout_count = max(1, int(np.ceil(len(stations) * 0.2)))
    holdout_stations = set(stations[-holdout_count:])
    test_mask = data["station_id"].astype(str).isin(holdout_stations)
    remaining = data.loc[~test_mask].reset_index(drop=True)
    remaining_splits, time_details = split_by_time(remaining)
    splits = {
        "train": remaining_splits["train"],
        "validation": remaining_splits["validation"],
        "test": data.loc[test_mask].reset_index(drop=True),
    }
    details = {
        "mode": "station",
        "holdout_stations": sorted(holdout_stations),
        "train_years": time_details["train_years"],
        "validation_year": time_details["validation_year"],
        "test_years": sorted(
            pd.to_datetime(splits["test"]["timestamp"], utc=True).dt.year.unique().tolist()
        ),
    }
    for name, split in splits.items():
        _require_years(split.index, name)
    return splits, details


def load_prepared_split(data_dir: Path, split: str) -> pd.DataFrame:
    if split not in {"train", "validation", "test"}:
        raise ValueError(f"Unsupported split: {split}")
    path = data_dir / f"{split}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Prepared split does not exist: {path}")
    return pd.read_csv(path)
