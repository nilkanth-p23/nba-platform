import json
import os
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
VERSIONS = ("pregame_v1", "player_props_v1", "live_win_v1")


@lru_cache(maxsize=1)
def load_models():
    pregame_dir = Path(os.getenv("PREGAME_MODEL_DIR", str(MODEL_DIR)))
    return {
        name: (
            joblib.load(directory / f"{name}.joblib"),
            json.loads((directory / f"{name}.json").read_text()),
        )
        for name in VERSIONS
        for directory in [pregame_dir if name == "pregame_v1" else MODEL_DIR]
    }


def calibrated(bundle, features):
    raw = np.clip(bundle["model"].predict_proba(features[bundle["features"]])[:, 1],
                  1e-6, 1 - 1e-6)
    return bundle["calibrator"].predict_proba(np.log(raw / (1 - raw)).reshape(-1, 1))[:, 1]
