"""Evaluate a saved P0 model with the fixed metric implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from src.data import FEATURE_COLUMNS, LABEL_COLUMN, load_prepared_split
from src.metrics import regression_metrics


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "validation", "test"), required=True)
    parser.add_argument("--output", type=Path)
    return parser


def _build_strata(frame: pd.DataFrame) -> dict[str, object]:
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    seasons = timestamps.dt.month.map(
        lambda month: {
            12: "winter",
            1: "winter",
            2: "winter",
            3: "spring",
            4: "spring",
            5: "spring",
            6: "summer",
            7: "summer",
            8: "summer",
            9: "autumn",
            10: "autumn",
            11: "autumn",
        }[int(month)]
    )
    qa_bins = pd.cut(
        frame["qa_value"],
        bins=[-float("inf"), 0.5, 0.75, float("inf")],
        labels=["low_lt_0_5", "medium_0_5_to_0_75", "high_ge_0_75"],
    ).astype("string")
    return {
        "season": seasons.to_numpy(),
        "surface_type": frame["surface_type"].astype(str).to_numpy(),
        "station_id": frame["station_id"].astype(str).to_numpy(),
        "qa_bin": qa_bins.to_numpy(),
    }


def main() -> None:
    args = _parser().parse_args()
    model_path = args.artifact_dir / "model.joblib"
    if not model_path.exists():
        raise FileNotFoundError(f"Model artifact does not exist: {model_path}")
    model = joblib.load(model_path)
    frame = load_prepared_split(args.data_dir, args.split)
    predictions = model.predict(frame[FEATURE_COLUMNS])
    strata = _build_strata(frame)
    labels = frame[LABEL_COLUMN].to_numpy()
    metrics = regression_metrics(
        labels,
        predictions,
        strata=strata,
    )
    official_baseline = regression_metrics(
        labels,
        frame["satellite_aod"].to_numpy(dtype=float),
        strata=strata,
    )
    result = {
        "split": args.split,
        "artifact_dir": str(args.artifact_dir),
        "metrics": metrics,
        "official_satellite_baseline": official_baseline,
    }
    output_path = args.output or args.artifact_dir / f"{args.split}_metrics.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
