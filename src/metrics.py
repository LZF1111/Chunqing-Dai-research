"""Fixed regression metrics for AOD evaluation."""

from __future__ import annotations

from typing import Mapping

import numpy as np


def _safe_r2(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    denominator = float(np.sum((y_true - np.mean(y_true)) ** 2))
    if denominator == 0.0:
        return None
    return float(1.0 - np.sum((y_true - y_pred) ** 2) / denominator)


def _safe_correlation(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    if y_true.size < 2 or np.std(y_true) == 0.0 or np.std(y_pred) == 0.0:
        return None
    return float(np.corrcoef(y_true, y_pred)[0, 1])


def _error_summary(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, object]:
    residual = y_pred - y_true
    return {
        "sample_count": int(y_true.size),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "mae": float(np.mean(np.abs(residual))),
        "bias": float(np.mean(residual)),
    }


def _grouped_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    labels: object,
) -> dict[str, object]:
    values = np.asarray(labels, dtype=object)
    if values.shape[0] != y_true.shape[0]:
        raise ValueError("Stratum labels must have the same length as y_true")
    groups: dict[str, object] = {}
    for raw_value in sorted({str(value) for value in values}):
        mask = np.asarray([str(value) == raw_value for value in values])
        groups[raw_value] = _error_summary(y_true[mask], y_pred[mask])
    return groups


def regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    strata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    true = np.asarray(y_true, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must have the same shape")
    if true.size == 0:
        raise ValueError("Cannot evaluate an empty split")

    metrics: dict[str, object] = {
        "sample_count": int(true.size),
        "rmse": float(np.sqrt(np.mean((pred - true) ** 2))),
        "mae": float(np.mean(np.abs(pred - true))),
        "bias": float(np.mean(pred - true)),
        "r2": _safe_r2(true, pred),
        "pearson_r": _safe_correlation(true, pred),
    }
    bins = {
        "low_lt_0_2": true < 0.2,
        "medium_0_2_to_0_5": (true >= 0.2) & (true < 0.5),
        "high_ge_0_5": true >= 0.5,
    }
    by_bin: dict[str, object] = {}
    for name, mask in bins.items():
        count = int(np.sum(mask))
        by_bin[name] = {"sample_count": count}
        if count:
            by_bin[name].update(_error_summary(true[mask], pred[mask]))
    metrics["by_true_aod_bin"] = by_bin
    if strata:
        metrics["by_stratum"] = {
            name: _grouped_metrics(true, pred, labels)
            for name, labels in strata.items()
        }
    return metrics
