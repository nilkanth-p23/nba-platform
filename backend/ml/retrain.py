"""Evaluate a pregame candidate on completed dates beyond the incumbent's training cutoff."""

import argparse
import json
from pathlib import Path

import joblib
import mlflow
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from xgboost import XGBClassifier

from app.db import engine
from app.model_loader import calibrated, load_models
from ml.features import build_features


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--incumbent-trained-through", type=pd.Timestamp, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    incumbent, meta = load_models()["pregame_v1"]
    cutoff = (pd.Timestamp(meta["trained_through"]) if "trained_through" in meta
              else args.incumbent_trained_through)
    games = pd.read_sql("select * from games where home_win is not null", engine,
                        parse_dates=["game_date"])
    features = incumbent["features"]
    table = build_features(games, pd.read_sql("select * from team_game_stats", engine))
    dates = sorted(table.game_date.unique())
    recent = [day for day in dates if day > cutoff]
    if len(recent) < 14:
        print("Need at least 14 completed game dates beyond the incumbent's training cutoff.")
        return
    holdout_start = recent[-14]
    earlier = [day for day in dates if day < holdout_start]
    calibration_start = earlier[-28]
    train = table[table.game_date < calibration_start]
    calibration = table[table.game_date.between(calibration_start, holdout_start, inclusive="left")]
    test = table[table.game_date >= holdout_start]
    params = incumbent["model"].get_params()
    params.pop("early_stopping_rounds", None)
    candidate = XGBClassifier(**params).fit(train[features], train.home_win.astype(int))
    raw = np.clip(candidate.predict_proba(calibration[features])[:, 1], 1e-6, 1 - 1e-6)
    cal = LogisticRegression().fit(np.log(raw / (1 - raw)).reshape(-1, 1),
                                  calibration.home_win.astype(int))
    bundle = {"model": candidate, "calibrator": cal, "features": features}
    candidate_brier = brier_score_loss(test.home_win, calibrated(bundle, test))
    incumbent_brier = brier_score_loss(test.home_win, calibrated(incumbent, test))
    if args.output.exists():
        parser.error("Choose a new output directory for this run.")
    mlflow.set_experiment("pregame-retraining")
    with mlflow.start_run():
        mlflow.log_params({"holdout_start": str(holdout_start), "training_cutoff": str(cutoff)})
        mlflow.log_metrics({"candidate_brier": candidate_brier, "incumbent_brier": incumbent_brier,
                            "holdout_games": len(test)})
        print(f"Candidate Brier {candidate_brier:.4f}, incumbent {incumbent_brier:.4f}.")
        if candidate_brier <= incumbent_brier:
            args.output.mkdir(parents=True)
            joblib.dump(bundle, args.output / "pregame_v1.joblib")
            report = {"model_version": f"pregame_{test.game_date.max():%Y%m%d}",
                      "features": features, "trained_through": str(calibration.game_date.max().date()),
                      "holdout_start": str(test.game_date.min().date()),
                      "holdout_end": str(test.game_date.max().date()), "holdout_games": len(test),
                      "candidate_brier": candidate_brier, "incumbent_brier": incumbent_brier,
                      "trained_on_seasons": sorted(
                          table.loc[table.game_date < holdout_start, "season"].unique())}
            (args.output / "pregame_v1.json").write_text(json.dumps(report, indent=2))
            mlflow.log_artifact(str(args.output / "pregame_v1.json"))
            print(f"Candidate eligible for review: {args.output}")


if __name__ == "__main__":
    main()
