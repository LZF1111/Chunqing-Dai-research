"""Validate a collocated CSV and create deterministic benchmark splits."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from src.data import (
    BASELINE_COLUMN,
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    OPTIONAL_NUMERIC_COLUMNS,
    load_and_validate,
    sha256_file,
    split_by_station,
    split_by_time,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Collocated input CSV")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed"),
        help="Directory for train.csv, validation.csv and test.csv",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/manifest.json"),
        help="Path for the reproducibility manifest",
    )
    parser.add_argument(
        "--split-mode",
        choices=("time", "station"),
        default="time",
        help="Use future-year holdout or deterministic station holdout",
    )
    parser.add_argument(
        "--dataset-kind",
        choices=("real", "synthetic", "unknown"),
        default="unknown",
        help="Provenance label used by the audit gate",
    )
    parser.add_argument(
        "--collocation-metadata",
        type=Path,
        help="JSON sidecar describing the real-data product and matching protocol",
    )
    parser.add_argument("--validation-year", type=int)
    parser.add_argument("--test-year", type=int)
    return parser


def _load_collocation_metadata(path: Path | None, dataset_kind: str) -> dict[str, object]:
    if dataset_kind == "real" and path is None:
        raise ValueError(
            "Real data requires --collocation-metadata with product and matching details"
        )
    if path is None:
        return {"kind": dataset_kind}
    if not path.exists():
        raise FileNotFoundError(f"Collocation metadata does not exist: {path}")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("Collocation metadata must be a JSON object")
    if dataset_kind == "real":
        required = [
            "satellite_product",
            "satellite_product_version",
            "aeronet_version",
            "temporal_window_minutes",
            "spatial_window",
            "pixel_aggregation",
            "quality_rule_id",
            "source_files",
        ]
        missing = [key for key in required if key not in metadata]
        if missing:
            raise ValueError(
                "Real collocation metadata is missing: " + ", ".join(missing)
            )
        for key in (
            "satellite_product",
            "satellite_product_version",
            "aeronet_version",
            "pixel_aggregation",
            "quality_rule_id",
        ):
            value = metadata[key]
            if not isinstance(value, str) or not value.strip() or "TO_BE_FILLED" in value:
                raise ValueError(f"Real collocation metadata field {key} is not finalized")
        source_files = metadata["source_files"]
        if not isinstance(source_files, list) or not source_files:
            raise ValueError("source_files must be a non-empty list")
        for source in source_files:
            if not isinstance(source, dict):
                raise ValueError("Each source_files entry must be an object")
            source_name = source.get("name")
            source_hash = source.get("sha256")
            if not isinstance(source_name, str) or not source_name.strip():
                raise ValueError("Each source file needs a name")
            if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
                raise ValueError("Each source file needs a lowercase SHA-256 hash")
    return metadata


def main() -> None:
    args = _parser().parse_args()
    input_path = args.input.resolve()
    collocation_metadata = _load_collocation_metadata(
        args.collocation_metadata,
        args.dataset_kind,
    )
    accepted, rejected = load_and_validate(input_path)

    if args.split_mode == "station":
        splits, split_details = split_by_station(accepted)
    else:
        splits, split_details = split_by_time(
            accepted,
            validation_year=args.validation_year,
            test_year=args.test_year,
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in splits.items():
        frame.to_csv(args.output_dir / f"{name}.csv", index=False)

    rejected_path = args.manifest.parent / "rejected.csv"
    rejected_path.parent.mkdir(parents=True, exist_ok=True)
    rejected.to_csv(rejected_path, index=False)

    manifest = {
        "schema_version": "p0-collocations-v1",
        "dataset_kind": args.dataset_kind,
        "collocation_metadata": collocation_metadata,
        "source_name": input_path.name,
        "source_sha256": sha256_file(input_path),
        "rows_before_validation": int(len(accepted) + len(rejected)),
        "rows_after_validation": int(len(accepted)),
        "rejected_rows": int(len(rejected)),
        "split": split_details,
        "split_rows": {name: int(len(frame)) for name, frame in splits.items()},
        "label_column": LABEL_COLUMN,
        "baseline_column": BASELINE_COLUMN,
        "feature_columns": FEATURE_COLUMNS,
        "optional_feature_missing_rate": {
            column: float(accepted[column].isna().mean())
            for column in OPTIONAL_NUMERIC_COLUMNS
        },
        "rejected_path": rejected_path.name,
    }
    manifest["prepare_script_sha256"] = sha256_file(Path(__file__).resolve())
    manifest["processed_split_sha256"] = {
        name: sha256_file(args.output_dir / f"{name}.csv") for name in splits
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
