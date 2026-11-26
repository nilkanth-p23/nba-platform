import numpy as np
import pandas as pd

REG_SECONDS = 2880
FEATURES = [
    "margin", "sec_remaining", "period", "elo_diff",
    "margin_per_sqrt", "elo_fade",
]


def clock_to_seconds(clock):
    parts = clock.astype(str).str.extract(r"PT(\d+)M([\d.]+)S")
    return pd.to_numeric(parts[0], errors="coerce") * 60 + pd.to_numeric(
        parts[1], errors="coerce"
    )


def add_time_columns(df):
    period = df["period"]
    regulation = period <= 4
    df["elapsed"] = np.where(
        regulation,
        (period - 1) * 720 + (720 - df["clock_secs"]),
        REG_SECONDS + (period - 5) * 300 + (300 - df["clock_secs"]),
    )
    df["sec_remaining"] = np.where(
        regulation, REG_SECONDS - df["elapsed"], df["clock_secs"]
    )
    return df


def make_features(df):
    out = pd.DataFrame(index=df.index)
    out["margin"] = df["home_score"] - df["away_score"]
    out["sec_remaining"] = df["sec_remaining"]
    out["period"] = df["period"].clip(upper=5)
    out["elo_diff"] = df["elo_diff"]
    out["margin_per_sqrt"] = out["margin"] / \
        np.sqrt(out["sec_remaining"].clip(lower=1))
    out["elo_fade"] = out["elo_diff"] * (
        out["sec_remaining"].clip(upper=REG_SECONDS) / REG_SECONDS
    )
    return out[FEATURES]
