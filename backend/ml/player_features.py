import numpy as np
import pandas as pd

from app.db import engine
from ml.features import build_team_table

STATS = ["pts", "reb", "ast"]
ROLL_COLS = ["minutes", "pts", "reb", "ast", "fga", "fta", "tov"]
WINDOWS = (5, 10)

FEATURES = [f"{c}_r{w}" for c in ROLL_COLS for w in WINDOWS]
FEATURES += [
    "minutes_season", "pts_season", "reb_season", "ast_season",
    "games_this_season", "minutes_trend", "minutes_last",
    "rest_days", "back_to_back", "is_home",
    "opp_pts_allowed_r10", "opp_pace_r10",
]


def team_context(games, stats):
    t = build_team_table(games, stats)
    g = t.groupby("team_id")
    out = t[["game_id", "team_id"]].copy()
    out["opp_pts_allowed_r10"] = g["opp_pts"].transform(
        lambda s: s.shift(1).rolling(10, min_periods=3).mean()
    )
    out["opp_pace_r10"] = g["poss"].transform(
        lambda s: s.shift(1).rolling(10, min_periods=3).mean()
    )
    return out.rename(columns={"team_id": "opp_team_id"})


def build_player_table(logs, games, stats):
    logs = logs.copy()
    logs["game_date"] = pd.to_datetime(logs["game_date"])
    num = ["minutes", "pts", "reb", "ast", "fga", "fta", "tov"]
    logs[num] = logs[num].apply(pd.to_numeric, errors="coerce")
    logs = logs[logs["minutes"] > 0]
    logs = logs.merge(
        games[["game_id", "season", "home_team_id", "away_team_id"]], on="game_id"
    )
    logs["is_home"] = logs["is_home"].astype(bool)
    logs["opp_team_id"] = np.where(
        logs["is_home"], logs["away_team_id"], logs["home_team_id"]
    )
    logs = logs.sort_values(
        ["player_id", "game_date", "game_id"]).reset_index(drop=True)

    g = logs.groupby("player_id")
    for c in ROLL_COLS:
        for w in WINDOWS:
            # shift(1) keeps a game's own stats out of its own features
            logs[f"{c}_r{w}"] = g[c].transform(
                lambda s, w=w: s.shift(1).rolling(w, min_periods=3).mean()
            )

    sg = logs.groupby(["player_id", "season"])
    for c in ["minutes", "pts", "reb", "ast"]:
        logs[f"{c}_season"] = sg[c].transform(
            lambda s: s.shift(1).expanding(min_periods=3).mean()
        )
    logs["games_this_season"] = sg.cumcount()
    logs["minutes_trend"] = logs["minutes_r5"] - logs["minutes_r10"]
    logs["minutes_last"] = g["minutes"].shift(1)
    logs["rest_days"] = g["game_date"].diff().dt.days.fillna(7).clip(upper=7)
    logs["back_to_back"] = (logs["rest_days"] == 1).astype(int)
    logs["is_home"] = logs["is_home"].astype(int)

    ctx = team_context(games, stats)
    return logs.merge(ctx, on=["game_id", "opp_team_id"], how="left")


def load_player_table():
    logs = pd.read_sql("select * from player_game_logs",
                       engine, parse_dates=["game_date"])
    games = pd.read_sql(
        "select * from games where home_win is not null", engine, parse_dates=["game_date"]
    )
    stats = pd.read_sql("select * from team_game_stats", engine)
    return build_player_table(logs, games, stats)
