from xgboost import XGBClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.linear_model import LogisticRegression
from sklearn.impute import SimpleImputer
from sklearn.calibration import calibration_curve
import shap
import pandas as pd
import numpy as np
import mlflow.xgboost
import mlflow.sklearn
import mlflow
import matplotlib.pyplot as plt
import json
from datetime import date
from pathlib import Path

import joblib
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
META_COLS = ["game_id", "season", "game_date", "home_win"]


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


def fit_calibrator(p, y):
    return LogisticRegression().fit(logit(p), y)


def apply_calibrator(cal, p):
    return cal.predict_proba(logit(p))[:, 1]


def calibration_plot(y, p, title, path):
    frac, mean = calibration_curve(y, p, n_bins=8, strategy="quantile")
    plt.figure(figsize=(5, 5))
    plt.plot([0, 1], [0, 1], "--", color="gray")
    plt.plot(mean, frac, marker="o")
    plt.xlabel("Predicted home win probability")
    plt.ylabel("Actual home win rate")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()


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

    df = pd.read_parquet(FEATURES_PATH)
    feature_names = [c for c in df.columns if c not in META_COLS]
    df["y"] = df["home_win"].astype(int)

    train = df[df["season"].isin(TRAIN)]
    val = df[df["season"].isin(VAL)]
    test = df[df["season"].isin(TEST)]
    X_tr, y_tr = train[feature_names], train["y"]
    X_val, y_val = val[feature_names], val["y"]
    X_te, y_te = test[feature_names], test["y"]
    print(f"train {len(train)}, validation {len(val)}, test {len(test)} games")

    mlflow.set_tracking_uri("http://127.0.0.1:5001")
    mlflow.set_experiment("pregame-win")
    summary = {}

    # Baseline 1: always favor the home team at the training home win rate
    rate = float(y_tr.mean())
    with mlflow.start_run(run_name="baseline-home-rate"):
        m = {
            **metrics(y_val, np.full(len(y_val), rate), "val"),
            **metrics(y_te, np.full(len(y_te), rate), "test"),
        }
        mlflow.log_params({"model": "home_win_rate", "home_rate": rate})
        mlflow.log_metrics(m)
        summary["home baseline"] = m

    # Baseline 2: logistic regression on the Elo difference only
    elo = LogisticRegression().fit(train[["elo_diff"]].fillna(0), y_tr)
    with mlflow.start_run(run_name="baseline-elo"):
        m = {
            **metrics(y_val, elo.predict_proba(val[["elo_diff"]].fillna(0))[:, 1], "val"),
            **metrics(y_te, elo.predict_proba(test[["elo_diff"]].fillna(0))[:, 1], "test"),
        }
        mlflow.log_params({"model": "logistic_elo_only"})
        mlflow.log_metrics(m)
        summary["elo only"] = m

    # Logistic regression on all features
    logreg = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(C=0.1, max_iter=2000),
    ).fit(X_tr, y_tr)
    with mlflow.start_run(run_name="logreg-all-features"):
        m = {
            **metrics(y_val, logreg.predict_proba(X_val)[:, 1], "val"),
            **metrics(y_te, logreg.predict_proba(X_te)[:, 1], "test"),
        }
        mlflow.log_params({"model": "logistic_regression", "C": 0.1})
        mlflow.log_metrics(m)
        log_model(mlflow.sklearn, logreg)
        summary["logistic regression"] = m

    # XGBoost with early stopping on validation log loss
    params = dict(
        n_estimators=1000,
        learning_rate=0.03,
        max_depth=3,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        reg_lambda=5.0,
        eval_metric="logloss",
        early_stopping_rounds=50,
        random_state=42,
    )
    xgb = XGBClassifier(**params)
    xgb.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    best_n = int(xgb.best_iteration) + 1

    p_val_raw = xgb.predict_proba(X_val)[:, 1]
    p_te_raw = xgb.predict_proba(X_te)[:, 1]
    cal = fit_calibrator(p_val_raw, y_val)
    p_te_cal = apply_calibrator(cal, p_te_raw)

    with mlflow.start_run(run_name="xgboost-calibrated"):
        m = {
            **metrics(y_val, p_val_raw, "val"),
            **metrics(y_te, p_te_raw, "test"),
            **metrics(y_te, p_te_cal, "test_cal"),
        }
        mlflow.log_params({**params, "best_n_estimators": best_n})
        mlflow.log_metrics(m)

        cal_path = PLOT_DIR / "calibration_test.png"
        calibration_plot(
            y_te, p_te_cal, "Calibration on 2025-26 (test)", cal_path)
        mlflow.log_artifact(str(cal_path))

        shap_values = shap.TreeExplainer(xgb).shap_values(X_te)
        shap.summary_plot(shap_values, X_te, show=False, max_display=15)
        shap_path = PLOT_DIR / "shap_summary.png"
        plt.savefig(shap_path, dpi=120, bbox_inches="tight")
        plt.close()
        mlflow.log_artifact(str(shap_path))

        log_model(mlflow.xgboost, xgb, registered_name="pregame_win")
        summary["xgboost raw"] = {k: v for k, v in m.items() if k.startswith("test_")
                                  and not k.startswith("test_cal")}
        summary["xgboost calibrated"] = {
            k.replace("test_cal", "test"): v for k, v in m.items() if k.startswith("test_cal")
        }

        # Production model: same settings, refit on every completed and current game
        final_params = {k: v for k, v in params.items() if k !=
                        "early_stopping_rounds"}
        final_params["n_estimators"] = best_n
        final = XGBClassifier(**final_params).fit(df[feature_names], df["y"])
        joblib.dump(
            {"model": final, "calibrator": cal, "features": feature_names},
            MODEL_DIR / "pregame_v1.joblib",
        )
        meta = {
            "model_version": "pregame_v1",
            "features": feature_names,
            "trained_on_seasons": sorted(df["season"].unique().tolist()),
            "validation_season": VAL,
            "test_season": TEST,
            "test_metrics_calibrated": summary["xgboost calibrated"],
            "best_n_estimators": best_n,
            "calibration": "Platt scaling fit on 2024-25 validation predictions",
            "trained_on": date.today().isoformat(),
        }
        meta_path = MODEL_DIR / "pregame_v1.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        mlflow.log_artifact(str(meta_path))

    print("\nTest season results (lower log loss and Brier is better):")
    for name, vals in summary.items():
        print(
            f"{name:22s} log_loss {vals['test_log_loss']:.4f}  "
            f"brier {vals['test_brier']:.4f}  acc {vals['test_accuracy']:.3f}"
        )


if __name__ == "__main__":
    main()
