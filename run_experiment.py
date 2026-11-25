"""Run one bounded experiment and append a machine-readable record."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src.data import sha256_file
from train import MODEL_NAMES


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODEL_NAMES, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.json"))
    parser.add_argument("--program", type=Path, default=Path("program.md"))
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--results-file", type=Path, default=Path("results/experiments.jsonl"))
    parser.add_argument("--experiment-id")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-seconds", type=_timeout_seconds, default=600)
    parser.add_argument("--hypothesis", required=True, help="One-sentence experiment hypothesis")
    return parser


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _git_status() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _write_text(path: Path, content: str | bytes | None) -> None:
    if content is None:
        text = ""
    elif isinstance(content, bytes):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return
    else:
        text = content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _append_record(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _save_record(artifact_dir: Path, results_file: Path, record: dict[str, object]) -> None:
    _write_json(artifact_dir / "record.json", record)
    if not (artifact_dir / "verdict.json").exists():
        status = record.get("status")
        verdict_status = "pending_gate" if status == "success" else "run_failed"
        _write_json(
            artifact_dir / "verdict.json",
            {
                "experiment_id": record.get("experiment_id"),
                "status": verdict_status,
                "accepted": False,
                "reason": "The experiment must pass gate.py before it becomes a research result.",
            },
        )
    _append_record(results_file, record)


def _csv_row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return max(0, sum(1 for _ in csv.reader(handle)) - 1)


def _load_and_verify_manifest(manifest_path: Path, data_dir: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_rows = manifest.get("split_rows", {})
    expected_hashes = manifest.get("processed_split_sha256", {})
    for split in ("train", "validation", "test"):
        split_path = data_dir / f"{split}.csv"
        if not split_path.exists():
            raise FileNotFoundError(f"Prepared split does not exist: {split_path}")
        if split in expected_rows and _csv_row_count(split_path) != expected_rows[split]:
            raise ValueError(f"{split_path} does not match manifest row count")
        if split in expected_hashes and sha256_file(split_path) != expected_hashes[split]:
            raise ValueError(f"{split_path} does not match manifest SHA-256")
    return manifest


def _timeout_seconds(value: str) -> int:
    timeout = int(value)
    if timeout <= 0 or timeout > 600:
        raise argparse.ArgumentTypeError("timeout-seconds must be between 1 and 600")
    return timeout


def main() -> None:
    args = _parser().parse_args()
    experiment_id = args.experiment_id or datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    artifact_dir = args.artifact_root / experiment_id
    if artifact_dir.exists() and any(artifact_dir.iterdir()):
        raise FileExistsError(
            f"Experiment directory already contains files: {artifact_dir}. "
            "Choose a new experiment ID to preserve append-only audit history."
        )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.manifest.resolve()
    program_path = args.program.resolve()
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Data manifest does not exist: {manifest_path}. Run prepare.py first."
        )
    if not program_path.exists():
        raise FileNotFoundError(f"Program contract does not exist: {program_path}")
    manifest = _load_and_verify_manifest(manifest_path, args.data_dir)

    config = {
        "model": args.model,
        "seed": args.seed,
        "data_dir": str(args.data_dir),
        "manifest": str(manifest_path),
        "program": str(program_path),
        "timeout_seconds": args.timeout_seconds,
        "hypothesis": args.hypothesis,
    }
    config_text = json.dumps(config, ensure_ascii=False, sort_keys=True)
    config_sha256 = hashlib.sha256(config_text.encode("utf-8")).hexdigest()
    manifest_sha256 = sha256_file(manifest_path)
    program_sha256 = sha256_file(program_path)
    _write_text(artifact_dir / "config.json", config_text + "\n")
    _write_text(artifact_dir / "hypothesis.md", f"# Hypothesis\n\n{args.hypothesis}\n")
    _write_text(artifact_dir / "manifest.json", manifest_path.read_bytes())
    _write_text(artifact_dir / "program.md", program_path.read_bytes())
    _write_json(
        artifact_dir / "environment.json",
        {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
        },
    )

    train_script = Path(__file__).with_name("train.py")
    evaluate_script = Path(__file__).with_name("evaluate.py")
    record: dict[str, object] = {
        "experiment_id": experiment_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "seed": args.seed,
        "data_dir": str(args.data_dir),
        "artifact_dir": str(artifact_dir),
        "git_commit": _git_commit(),
        "git_status_before": _git_status(),
        "data_manifest_sha256": manifest_sha256,
        "dataset_kind": manifest.get("dataset_kind", "unknown"),
        "processed_split_sha256": manifest.get("processed_split_sha256", {}),
        "program_sha256": program_sha256,
        "config_sha256": config_sha256,
        "hypothesis": args.hypothesis,
        "status": "started",
    }
    start = time.monotonic()
    train_command = [
        sys.executable,
        str(train_script),
        "--model",
        args.model,
        "--data-dir",
        str(args.data_dir),
        "--artifact-dir",
        str(artifact_dir),
        "--seed",
        str(args.seed),
    ]
    _write_text(artifact_dir / "command.txt", " ".join(train_command) + "\n")
    try:
        training = subprocess.run(
            train_command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(0.1, args.timeout_seconds - (time.monotonic() - start)),
        )
    except subprocess.TimeoutExpired as error:
        _write_text(artifact_dir / "train.stdout.log", error.stdout)
        _write_text(artifact_dir / "train.stderr.log", error.stderr)
        record.update(
            {
                "status": "timeout",
                "duration_seconds": round(time.monotonic() - start, 3),
                "error": f"training exceeded {args.timeout_seconds} seconds",
                "stdout_tail": _write_text_tail(error.stdout),
                "stderr_tail": _write_text_tail(error.stderr),
            }
        )
        _save_record(artifact_dir, args.results_file, record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        raise SystemExit(124)

    _write_text(artifact_dir / "train.stdout.log", training.stdout)
    _write_text(artifact_dir / "train.stderr.log", training.stderr)
    if training.returncode != 0:
        record.update(
            {
                "status": "training_failed",
                "duration_seconds": round(time.monotonic() - start, 3),
                "return_code": training.returncode,
                "stdout_tail": training.stdout[-2000:],
                "stderr_tail": training.stderr[-2000:],
            }
        )
        _save_record(artifact_dir, args.results_file, record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        raise SystemExit(training.returncode)

    metrics_path = artifact_dir / "validation_metrics.json"
    evaluation_command = [
        sys.executable,
        str(evaluate_script),
        "--data-dir",
        str(args.data_dir),
        "--artifact-dir",
        str(artifact_dir),
        "--split",
        "validation",
        "--output",
        str(metrics_path),
    ]
    with (artifact_dir / "command.txt").open("a", encoding="utf-8") as handle:
        handle.write(" ".join(evaluation_command) + "\n")
    try:
        evaluation = subprocess.run(
            evaluation_command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(0.1, args.timeout_seconds - (time.monotonic() - start)),
        )
    except subprocess.TimeoutExpired as error:
        _write_text(artifact_dir / "evaluate.stdout.log", error.stdout)
        _write_text(artifact_dir / "evaluate.stderr.log", error.stderr)
        record.update(
            {
                "status": "evaluation_timeout",
                "error": "validation evaluation exceeded its timeout",
                "stdout_tail": _write_text_tail(error.stdout),
                "stderr_tail": _write_text_tail(error.stderr),
            }
        )
        record["duration_seconds"] = round(time.monotonic() - start, 3)
        _save_record(artifact_dir, args.results_file, record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        raise SystemExit(124)

    _write_text(artifact_dir / "evaluate.stdout.log", evaluation.stdout)
    _write_text(artifact_dir / "evaluate.stderr.log", evaluation.stderr)
    record["duration_seconds"] = round(time.monotonic() - start, 3)
    if evaluation.returncode != 0:
        record.update(
            {
                "status": "evaluation_failed",
                "return_code": evaluation.returncode,
                "stdout_tail": evaluation.stdout[-2000:],
                "stderr_tail": evaluation.stderr[-2000:],
            }
        )
    else:
        record.update(
            {
                "status": "success",
                "metrics": json.loads(metrics_path.read_text(encoding="utf-8"))["metrics"],
            }
        )
    record["git_status_after"] = _git_status()
    _save_record(artifact_dir, args.results_file, record)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    if record["status"] != "success":
        raise SystemExit(1)


def _write_text_tail(content: str | bytes | None) -> str:
    if content is None:
        return ""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    return content[-2000:]


if __name__ == "__main__":
    main()
