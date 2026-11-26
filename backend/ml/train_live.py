from ml.live_features import FEATURES, add_time_columns, clock_to_seconds, make_features
from app.db import engine
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.linear_model import LogisticRegression
import pandas as pd
import numpy as np
import mlflow.lightgbm
import mlflow
import matplotlib.pyplot as plt
import json
from datetime import date
from pathlib import Path

import joblib
import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")


BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
FEATURES_PATH = ROOT / "data" / "raw" / "features.parquet"
PLOT_DIR = ROOT / "data" / "raw" / "plots"
MODEL_DIR = BACKEND / "models"

TRAIN = ["2021-22", "2022-23", "2023-24"]
VAL = ["2024-25"]
TEST = ["2025-26"]
BUCKET_SECONDS = 30


def load_states():
    feats = pd.read_parquet(
        FEATURES_PATH, columns=["game_id", "season", "elo_diff", "home_win"]
    )
    pbp = pd.read_sql(
        "select game_id, event_num, period, clock, home_score, away_score from pbp_events",
        engine,
    )
    pbp = pbp.merge(feats, on="game_id")
    pbp["clock_secs"] = clock_to_seconds(pbp["clock"])
    pbp = pbp.dropna(subset=["clock_secs", "elo_diff"])
    pbp = add_time_columns(pbp)
    pbp = pbp[pbp["sec_remaining"] > 0].sort_values(["game_id", "event_num"])
    pbp["bucket"] = (pbp["elapsed"] // BUCKET_SECONDS).astype(int)
    # keep the last event in each 30-second slice of game time
    states = pbp.groupby(["game_id", "bucket"]).tail(1).copy()
    states["y"] = states["home_win"].astype(int)
    return states


def metrics(y, p, prefix):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        f"{prefix}_log_loss": float(log_loss(y, p)),
        f"{prefix}_brier": float(brier_score_loss(y, p)),
        f"{prefix}_accuracy": float(accuracy_score(y, p > 0.5)),
    }


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)).reshape(-1, 1)


def log_model(flavor, model, registered_name=None):
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
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    states = load_states()
    X = make_features(states)
    y = states["y"]

    tr = states["season"].isin(TRAIN).values
    va = states["season"].isin(VAL).values
    te = states["season"].isin(TEST).values
    print(
        f"train {tr.sum()}, validation {va.sum()}, test {te.sum()} game states")
    if va.sum() == 0 or te.sum() == 0:
        print("Validation or test season has no play-by-play yet. "
              "Wait for the download to finish and run this again.")
        return

    mlflow.set_tracking_uri("http://127.0.0.1:5001")
    mlflow.set_experiment("live-win")
    summary = {}

    base_cols = ["margin_per_sqrt", "elo_fade"]
    base = LogisticRegression(max_iter=1000).fit(X[tr][base_cols], y[tr])
    with mlflow.start_run(run_name="baseline-logistic"):
        m = {
            **metrics(y[va], base.predict_proba(X[va][base_cols])[:, 1], "val"),
            **metrics(y[te], base.predict_proba(X[te][base_cols])[:, 1], "test"),
        }
        mlflow.log_params(
            {"model": "logistic", "features": ",".join(base_cols)})
        mlflow.log_metrics(m)
        summary["logistic baseline"] = m

    params = dict(
        n_estimators=1000, learning_rate=0.05, num_leaves=31,
        min_child_samples=200, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, random_state=42, verbose=-1,
    )
    model = lgb.LGBMClassifier(**params)
    model.fit(
        X[tr], y[tr], eval_set=[(X[va], y[va])], eval_metric="binary_logloss",
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    best_n = int(model.best_iteration_ or params["n_estimators"])
    p_val = model.predict_proba(X[va])[:, 1]
    p_te = model.predict_proba(X[te])[:, 1]

    cal = LogisticRegression().fit(logit(p_val), y[va])
    p_te_cal = cal.predict_proba(logit(p_te))[:, 1]

    test_df = states[te].copy()
    test_df["p"] = p_te_cal
    test_df["margin"] = test_df["home_score"] - test_df["away_score"]

    with mlflow.start_run(run_name="lightgbm-calibrated"):
        m = {
            **metrics(y[va], p_val, "val"),
            **metrics(y[te], p_te, "test"),
            **metrics(y[te], p_te_cal, "test_cal"),
        }
        mlflow.log_params({**params, "best_n_estimators": best_n,
                           "bucket_seconds": BUCKET_SECONDS})
        mlflow.log_metrics(m)
        summary["lightgbm raw"] = {k: v for k, v in m.items()
                                   if k.startswith("test_") and not k.startswith("test_cal")}
        summary["lightgbm calibrated"] = {
            k.replace("test_cal", "test"): v for k, v in m.items() if k.startswith("test_cal")
        }

        # Calibration by quarter: average predicted vs actual home win rate
        fig, axes = plt.subplots(1, 4, figsize=(16, 4), sharey=True)
        for ax, period in zip(axes, [1, 2, 3, 4]):
            sub = test_df[test_df["period"] == period]
            bins = pd.qcut(sub["p"], 10, duplicates="drop")
            grp = sub.groupby(bins, observed=True).agg(
                pred=("p", "mean"), actual=("y", "mean"))
            ax.plot([0, 1], [0, 1], "--", color="gray")
            ax.plot(grp["pred"], grp["actual"], marker="o")
            ax.set_title(f"Quarter {period}")
            ax.set_xlabel("Predicted")
        axes[0].set_ylabel("Actual home win rate")
        plt.tight_layout()
        cal_path = PLOT_DIR / "live_calibration_by_quarter.png"
        plt.savefig(cal_path, dpi=120)
        plt.close()
        mlflow.log_artifact(str(cal_path))

        # Win probability curve for the biggest comeback in the test season
        test_df["winner_margin"] = np.where(
            test_df["y"] == 1, test_df["margin"], -test_df["margin"])
        game_id = test_df.groupby("game_id")["winner_margin"].min().idxmin()
        g = test_df[test_df["game_id"] == game_id].sort_values("elapsed")
        plt.figure(figsize=(8, 4))
        plt.plot(g["elapsed"] / 60, g["p"])
        plt.axhline(0.5, color="gray", linestyle="--")
        plt.ylim(0, 1)
        plt.xlabel("Game minutes elapsed")
        plt.ylabel("Home win probability")
        plt.title(f"Biggest comeback in the test season (game {game_id})")
        plt.tight_layout()
        curve_path = PLOT_DIR / "live_win_curve.png"
        plt.savefig(curve_path, dpi=120)
        plt.close()
        mlflow.log_artifact(str(curve_path))

        log_model(mlflow.lightgbm, model, registered_name="live_win")

        # Production model: refit on every season
        final = lgb.LGBMClassifier(
            **{**params, "n_estimators": best_n}).fit(X, y)
        joblib.dump({"model": final, "calibrator": cal, "features": FEATURES},
                    MODEL_DIR / "live_win_v1.joblib")
        meta = {
            "model_version": "live_win_v1",
            "features": FEATURES,
            "trained_on_seasons": sorted(states["season"].unique().tolist()),
            "validation_season": VAL,
            "test_season": TEST,
            "bucket_seconds": BUCKET_SECONDS,
            "test_metrics_calibrated": summary["lightgbm calibrated"],
            "best_n_estimators": best_n,
            "trained_on": date.today().isoformat(),
        }
        meta_path = MODEL_DIR / "live_win_v1.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        mlflow.log_artifact(str(meta_path))

    print("\nTest season results (lower log loss and Brier is better):")
    for name, vals in summary.items():
        print(f"{name:22s} log_loss {vals['test_log_loss']:.4f}  "
              f"brier {vals['test_brier']:.4f}  acc {vals['test_accuracy']:.3f}")

    print("\nCalibrated model by quarter (test season):")
    for period in [1, 2, 3, 4]:
        sub = test_df[test_df["period"] == period]
        print(f"Q{period}: log_loss {log_loss(sub['y'], sub['p']):.4f}  "
              f"acc {accuracy_score(sub['y'], sub['p'] > 0.5):.3f}  "
              f"mean predicted {sub['p'].mean():.3f}  actual {sub['y'].mean():.3f}")
    late = test_df[test_df["sec_remaining"] <= 120]
    print(
        f"Last 2 minutes: acc {accuracy_score(late['y'], late['p'] > 0.5):.3f}")


if __name__ == "__main__":
    main()
