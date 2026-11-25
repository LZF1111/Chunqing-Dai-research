"""Baseline models and shared preprocessing for the P0 benchmark."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .data import BASELINE_COLUMN, CATEGORICAL_FEATURES, NUMERIC_FEATURES


class ConstantRegressor:
    """Predict the mean value of the training labels."""

    def fit(self, _features: pd.DataFrame, labels: pd.Series) -> "ConstantRegressor":
        self.constant_ = float(np.mean(labels))
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        if not hasattr(self, "constant_"):
            raise RuntimeError("ConstantRegressor must be fitted before prediction")
        return np.full(len(features), self.constant_, dtype=float)


class SatelliteAODRegressor:
    """Use the official satellite AOD as an explicit business baseline."""

    def fit(self, _features: pd.DataFrame, _labels: pd.Series) -> "SatelliteAODRegressor":
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return features[BASELINE_COLUMN].to_numpy(dtype=float)


def _preprocessor() -> ColumnTransformer:
    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("one_hot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("numeric", numeric, NUMERIC_FEATURES),
            ("categorical", categorical, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )


def build_model(name: str, random_state: int) -> Any:
    if name == "mean":
        return ConstantRegressor()
    if name == "satellite":
        return SatelliteAODRegressor()

    preprocessor = _preprocessor()
    if name == "ridge":
        estimator = Ridge(alpha=1.0)
    elif name == "random_forest":
        estimator = RandomForestRegressor(
            n_estimators=200,
            min_samples_leaf=2,
            random_state=random_state,
            n_jobs=-1,
        )
    elif name == "mlp":
        estimator = MLPRegressor(
            hidden_layer_sizes=(64, 32),
            max_iter=500,
            early_stopping=True,
            random_state=random_state,
        )
    else:
        raise ValueError(
            f"Unsupported model {name!r}. Choose mean, satellite, ridge, random_forest or mlp."
        )
    return Pipeline(steps=[("preprocessor", preprocessor), ("estimator", estimator)])
