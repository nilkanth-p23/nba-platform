import json
from datetime import date
from pathlib import Path

import joblib
import lightgbm as lgb
import mlflow
import mlflow.lightgbm
import numpy as np
from sklearn.metrics import mean_absolute_error

from ml.player_features import FEATURES, STATS, load_player_table

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
TRAIN = ["2021-22", "2022-23", "2023-24"]
VAL = ["2024-25"]
TEST = ["2025-26"]
MIN_MINUTES = 12

BASE = dict(
    n_estimators=1000,
    learning_rate=0.03,
    num_leaves=15,
    min_child_samples=50,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=5.0,
    random_state=42,
    verbose=-1,
)


def log_model(flavor, model, registered_name):
    try:
        try:
            flavor.log_model(model, name="model",
                             registered_model_name=registered_name)
        except TypeError:
            flavor.log_model(model, artifact_path="model",
                             registered_model_name=registered_name)
    except Exception as exc:
        print(f"warning: could not log model to MLflow: {exc}")


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = load_player_table()
    needed = ["minutes_r10"] + [f"{s}_r10" for s in STATS] + STATS
    df = df[df["minutes_r10"] >= MIN_MINUTES].dropna(subset=needed)

    train = df[df["season"].isin(TRAIN)]
    val = df[df["season"].isin(VAL)]
    test = df[df["season"].isin(TEST)]
    print(
        f"train {len(train)}, validation {len(val)}, test {len(test)} player-games")

    mlflow.set_tracking_uri("http://127.0.0.1:5001")
    mlflow.set_experiment("player-props")

    summary, production, metadata = {}, {"features": FEATURES}, {}

    for stat in STATS:
        y_tr, y_val, y_te = train[stat], val[stat], test[stat]
        base_val = mean_absolute_error(y_val, val[f"{stat}_r10"])
        base_te = mean_absolute_error(y_te, test[f"{stat}_r10"])

        model = lgb.LGBMRegressor(objective="regression", metric="l1", **BASE)
        model.fit(
            train[FEATURES], y_tr,
            eval_set=[(val[FEATURES], y_val)],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
        best_n = int(model.best_iteration_ or BASE["n_estimators"])
        mae_val = mean_absolute_error(y_val, model.predict(val[FEATURES]))
        mae_te = mean_absolute_error(y_te, model.predict(test[FEATURES]))

        fixed = {**BASE, "n_estimators": best_n}
        q_models = {
            name: lgb.LGBMRegressor(objective="quantile", alpha=a, **fixed).fit(
                train[FEATURES], y_tr
            )
            for name, a in (("q10", 0.1), ("q90", 0.9))
        }
        lo = q_models["q10"].predict(test[FEATURES])
        hi = q_models["q90"].predict(test[FEATURES])
        coverage = float(np.mean((y_te.values >= lo) & (y_te.values <= hi)))

        with mlflow.start_run(run_name=f"props-{stat}"):
            mlflow.log_params({
                "stat": stat,
                "min_minutes_r10": MIN_MINUTES,
                "best_n_estimators": best_n,
                **{k: v for k, v in BASE.items() if k != "verbose"},
            })
            m = {
                "val_mae": float(mae_val),
                "test_mae": float(mae_te),
                "val_baseline_mae": float(base_val),
                "test_baseline_mae": float(base_te),
                "test_interval_coverage": coverage,
            }
            mlflow.log_metrics(m)
            log_model(mlflow.lightgbm, model, f"player_props_{stat}")

        # Production models: same settings, refit on every season
        production[stat] = {
            "mean": lgb.LGBMRegressor(objective="regression", **fixed).fit(
                df[FEATURES], df[stat]
            ),
            "q10": lgb.LGBMRegressor(objective="quantile", alpha=0.1, **fixed).fit(
                df[FEATURES], df[stat]
            ),
            "q90": lgb.LGBMRegressor(objective="quantile", alpha=0.9, **fixed).fit(
                df[FEATURES], df[stat]
            ),
        }
        summary[stat] = m
        metadata[stat] = {**m, "best_n_estimators": best_n}

    joblib.dump(production, MODEL_DIR / "player_props_v1.joblib")
    (MODEL_DIR / "player_props_v1.json").write_text(json.dumps({
        "model_version": "player_props_v1",
        "features": FEATURES,
        "trained_on_seasons": sorted(df["season"].unique().tolist()),
        "validation_season": VAL,
        "test_season": TEST,
        "min_minutes_r10": MIN_MINUTES,
        "metrics": metadata,
        "trained_on": date.today().isoformat(),
    }, indent=2))

    print("\nTest season results (mean absolute error, lower is better):")
    for stat, m in summary.items():
        gain = 100 * (1 - m["test_mae"] / m["test_baseline_mae"])
        print(
            f"{stat:4s} baseline {m['test_baseline_mae']:.3f}  model {m['test_mae']:.3f}  "
            f"improvement {gain:.1f}%  80% interval coverage {m['test_interval_coverage']:.3f}"
        )


if __name__ == "__main__":
    main()
