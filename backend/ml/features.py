import json
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import delete

from app.db import SessionLocal, engine
from app.models import GameFeatures
from pipelines.common import insert_ignore

WINDOWS = (5, 10)
ELO_START, ELO_K, ELO_HOME, ELO_CARRY = 1500.0, 20.0, 100.0, 0.75
METRICS = ["pts", "opp_pts", "margin", "efg", "tov_rate", "reb_rate",
           "poss", "net_rating", "win"]
OUT_PATH = Path(__file__).resolve(
).parents[2] / "data" / "raw" / "features.parquet"
NUMERIC = ["pts", "fgm", "fga", "fg3m", "ftm", "fta", "oreb", "reb", "tov",
           "opp_pts", "opp_fga", "opp_fta", "opp_oreb", "opp_tov", "opp_reb"]


def build_team_table(games, stats):
    opp_cols = ["game_id", "team_id", "pts",
                "fga", "fta", "oreb", "tov", "reb"]
    opp = stats[opp_cols].rename(
        columns={c: f"opp_{c}" for c in opp_cols if c != "game_id"}
    )
    df = stats.merge(
        games[["game_id", "season", "game_date", "home_win"]], on="game_id")
    df = df.merge(opp, on="game_id")
    df = df[df["team_id"] != df["opp_team_id"]].copy()
    df[NUMERIC] = df[NUMERIC].apply(pd.to_numeric, errors="coerce")
    df["is_home"] = df["is_home"].astype(bool)
    df["win"] = (df["is_home"] == df["home_win"].astype(bool)).astype(int)
    df["margin"] = df["pts"] - df["opp_pts"]
    df["poss"] = df["fga"] + 0.44 * df["fta"] - df["oreb"] + df["tov"]
    df["efg"] = (df["fgm"] + 0.5 * df["fg3m"]) / df["fga"]
    df["tov_rate"] = df["tov"] / df["poss"]
    df["reb_rate"] = df["reb"] / (df["reb"] + df["opp_reb"])
    df["net_rating"] = 100 * df["margin"] / df["poss"]
    return df.sort_values(["game_date", "game_id"]).reset_index(drop=True)


def games_in_last_7(dates):
    d = dates.values.astype("datetime64[D]").astype("int64")
    counts = np.arange(len(d)) - np.searchsorted(d, d - 7, side="left")
    return pd.Series(counts, index=dates.index)


def compute_elo(games):
    ratings, last_season, out = {}, None, []
    for g in games.sort_values(["game_date", "game_id"]).itertuples():
        if g.season != last_season:
            ratings = {t: ELO_START + ELO_CARRY *
                       (r - ELO_START) for t, r in ratings.items()}
            last_season = g.season
        rh = ratings.get(g.home_team_id, ELO_START)
        ra = ratings.get(g.away_team_id, ELO_START)
        expected = 1 / (1 + 10 ** (-((rh + ELO_HOME) - ra) / 400))
        out.append((g.game_id, rh, ra))
        delta = ELO_K * ((1.0 if g.home_win else 0.0) - expected)
        ratings[g.home_team_id] = rh + delta
        ratings[g.away_team_id] = ra - delta
    return pd.DataFrame(out, columns=["game_id", "elo_home", "elo_away"])


def build_features(games, stats):
    games = games.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    df = build_team_table(games, stats)

    for m in METRICS:
        grp = df.groupby("team_id")[m]
        for w in WINDOWS:
            # shift(1) keeps a game's own result out of its own features
            df[f"{m}_r{w}"] = grp.transform(
                lambda s, w=w: s.shift(1).rolling(w, min_periods=3).mean()
            )

    by_season = df.groupby(["team_id", "season"])
    games_before = by_season.cumcount()
    wins_before = by_season["win"].cumsum() - df["win"]
    df["season_win_pct"] = np.where(
        games_before > 0, wins_before / games_before.clip(lower=1), np.nan)

    df["rest_days"] = df.groupby("team_id")["game_date"].diff().dt.days
    df["rest_days"] = df["rest_days"].fillna(7).clip(upper=7)
    df["back_to_back"] = (df["rest_days"] == 1).astype(int)
    df["games_last_7"] = df.groupby("team_id", group_keys=False)[
        "game_date"].apply(games_in_last_7)

    feat_cols = [f"{m}_r{w}" for m in METRICS for w in WINDOWS]
    feat_cols += ["season_win_pct", "rest_days",
                  "back_to_back", "games_last_7"]

    home = df[df["is_home"]].set_index(
        "game_id")[feat_cols].add_prefix("home_")
    away = df[~df["is_home"]].set_index(
        "game_id")[feat_cols].add_prefix("away_")
    wide = home.join(away, how="inner")
    for c in feat_cols:
        wide[f"diff_{c}"] = wide[f"home_{c}"] - wide[f"away_{c}"]
    keep = [f"diff_{c}" for c in feat_cols]
    keep += ["home_rest_days", "away_rest_days",
             "home_back_to_back", "away_back_to_back"]
    wide = wide[keep]

    elo = compute_elo(games).set_index("game_id")
    wide["elo_diff"] = elo["elo_home"] - elo["elo_away"]
    wide = wide.join(games.set_index("game_id")[
                     ["season", "game_date", "home_win"]])
    return wide.reset_index()


def main():
    games = pd.read_sql("select * from games where home_win is not null", engine,
                        parse_dates=["game_date"])
    stats = pd.read_sql("select * from team_game_stats", engine)
    wide = build_features(games, stats)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wide.to_parquet(OUT_PATH, index=False)

    names = [c for c in wide.columns if c not in (
        "game_id", "season", "game_date", "home_win")]
    records = json.loads(wide[names].to_json(orient="records"))
    rows = [
        {"game_id": gid, "features": feats, "home_win": bool(hw)}
        for gid, feats, hw in zip(wide["game_id"], records, wide["home_win"])
    ]
    with SessionLocal() as session:
        session.execute(delete(GameFeatures))
        session.commit()
        insert_ignore(session, GameFeatures, rows)
    print(f"{len(rows)} games, {len(names)} features")


if __name__ == "__main__":
    main()
