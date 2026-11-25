"""Train one P0 baseline and save a portable joblib artifact."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib

from src.data import FEATURE_COLUMNS, LABEL_COLUMN, load_prepared_split
from src.models import build_model


MODEL_NAMES = ("mean", "satellite", "ridge", "random_forest", "mlp")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODEL_NAMES, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main() -> None:
    args = _parser().parse_args()
    training = load_prepared_split(args.data_dir, "train")
    features = training[FEATURE_COLUMNS]
    labels = training[LABEL_COLUMN]
    model = build_model(args.model, random_state=args.seed)
    model.fit(features, labels)

    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.artifact_dir / "model.joblib"
    joblib.dump(model, model_path)
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "seed": args.seed,
        "training_rows": int(len(training)),
        "label_column": LABEL_COLUMN,
        "feature_columns": FEATURE_COLUMNS,
        "model_path": str(model_path),
    }
    (args.artifact_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
