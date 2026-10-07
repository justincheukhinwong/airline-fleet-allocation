"""Descriptive, departure-weighted aircraft-gauge benchmarks."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

def sum_with_missing(series: pd.Series) -> float:
    # Preserve missing when every value is missing.
    return series.sum(min_count=1)


def make_one_hot_encoder() -> OneHotEncoder:
    return OneHotEncoder(drop="first", handle_unknown="error", sparse_output=False)


def fit_weighted_gauge_model(
    data: pd.DataFrame,
    categorical_features: list[str],
    numeric_features: list[str],
    model_name: str,
) -> tuple[Pipeline, np.ndarray, dict[str, float]]:
    # Fit weighted OLS and return predictions plus readable fit metrics.
    features = categorical_features + numeric_features
    preprocessor = ColumnTransformer(
        transformers=[
            ("categorical", make_one_hot_encoder(), categorical_features),
            ("numeric", "passthrough", numeric_features),
        ],
        remainder="drop",
    )
    model = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", LinearRegression()),
        ]
    )

    weights = data["departures"].to_numpy()
    actual = data["seats_per_departure"].to_numpy()
    model.fit(
        data[features],
        actual,
        model__sample_weight=weights,
    )
    predicted = model.predict(data[features])

    weighted_mean = np.average(actual, weights=weights)
    squared_error = np.average((actual - predicted) ** 2, weights=weights)
    total_variation = np.average((actual - weighted_mean) ** 2, weights=weights)

    metrics = {
        "model": model_name,
        "evaluation": "In-sample, departure-weighted",
        "observations": int(len(data)),
        "departures": float(weights.sum()),
        "weighted_r_squared": float(1 - squared_error / total_variation),
        "weighted_mae_seats": float(
            np.average(np.abs(actual - predicted), weights=weights)
        ),
        "weighted_rmse_seats": float(np.sqrt(squared_error)),
    }
    return model, predicted, metrics


def coefficient_table(
    fitted_model: Pipeline,
    model_name: str,
) -> pd.DataFrame:
    feature_names = fitted_model.named_steps[
        "preprocessor"
    ].get_feature_names_out()
    coefficients = fitted_model.named_steps["model"].coef_
    table = pd.DataFrame(
        {
            "model": model_name,
            "feature": feature_names,
            "coefficient_seats": coefficients,
        }
    )
    table["feature"] = (
        table["feature"]
        .str.replace("categorical__", "", regex=False)
        .str.replace("numeric__", "", regex=False)
    )
    keep = (
        table["feature"].eq("log_monthly_departures")
        | table["feature"].str.startswith("YEAR_CAT_")
        | table["feature"].eq("log1p_freight_tonnes_per_departure")
    )
    return table.loc[keep].reset_index(drop=True)


def aggregate_expected_gauge(
    monthly_data: pd.DataFrame,
    expected_column: str,
    residual_column: str,
) -> pd.DataFrame:
    data = monthly_data.copy()
    data["expected_seat_capacity"] = (
        data[expected_column] * data["departures"]
    )
    data["residual_seat_capacity"] = (
        data[residual_column] * data["departures"]
    )

    grouped = (
        data.groupby(
            [
                "YEAR", "ROUTE", "UNIQUE_CARRIER",
                "UNIQUE_CARRIER_NAME", "US_AIRPORT", "ASIA_AIRPORT",
            ],
            observed=True,
        )
        .agg(
            departures=("departures", "sum"),
            seats=("seats", "sum"),
            passengers=("passengers", "sum"),
            expected_seat_capacity=("expected_seat_capacity", "sum"),
            residual_seat_capacity=("residual_seat_capacity", "sum"),
            months_operated=("MONTH", "nunique"),
            distance_miles=("distance_miles", "median"),
        )
        .reset_index()
    )
    grouped["actual_gauge"] = grouped["seats"] / grouped["departures"]
    grouped["expected_gauge"] = (
        grouped["expected_seat_capacity"] / grouped["departures"]
    )
    grouped["gauge_residual"] = (
        grouped["residual_seat_capacity"] / grouped["departures"]
    )
    grouped["passenger_load_factor"] = (
        grouped["passengers"] / grouped["seats"]
    )
    return grouped
