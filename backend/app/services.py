import re
from datetime import date

import pandas as pd
from nba_api.stats.static import players
from sqlalchemy import exists, select
from xgboost import DMatrix

from app.db import SessionLocal, engine
from app.feed import FEED_ERRORS, NBA_TEAMS, live_feed, schedule, today
from app.model_loader import calibrated, load_models
from app.models import Game, PbpEvent, PlayerGameLog
from ml.features import ELO_HOME, build_features
from ml.live_features import add_time_columns, clock_to_seconds, make_features
from ml.player_features import STATS, build_player_table


class DataUnavailable(Exception):
    pass


def named(game):
    return {**game, **{side: NBA_TEAMS.get(game[f"{side}_team_id"], {}).get(
        "full_name", str(game[f"{side}_team_id"])) for side in ("home", "away")}}


def archived(g):
    return named({"game_id": g.game_id, "game_date": g.game_date.isoformat(),
                  "home_team_id": g.home_team_id, "away_team_id": g.away_team_id,
                  "home_score": g.home_pts, "away_score": g.away_pts,
                  "status": "replay", "season": g.season, "source": "PostgreSQL archive"})


def game_list(day):
    warning = None
    games = []
    if day >= today():
        try:
            games = [named(g) for g in schedule(day)]
        except FEED_ERRORS:
            warning = "The live schedule is temporarily unavailable."
    with SessionLocal() as session:
        replay = session.scalars(select(Game).where(
            Game.home_win.is_not(None), Game.game_date <= day,
            exists().where(PbpEvent.game_id == Game.game_id),
        ).order_by(Game.game_date.desc(), Game.game_id).limit(6)).all()
    return {"date": day, "games": games, "replays": [archived(g) for g in replay],
            "warning": warning}


def matchup(game_id):
    if game_id.startswith("e"):
        try:
            game, _ = live_feed(game_id)
            return named(game)
        except FEED_ERRORS as exc:
            raise DataUnavailable("The live game feed is unavailable.") from exc
    with SessionLocal() as session:
        game = session.get(Game, game_id)
        if game is None:
            raise DataUnavailable("Game ID was not found in the archive.")
        return archived(game)


def matchup_frames(game):
    # Add an empty target row so the training feature builders apply the same shifts.
    target = pd.Timestamp(game["game_date"])
    games = pd.read_sql("select * from games where home_win is not null and game_date < %(day)s",
                        engine, params={"day": target.date()}, parse_dates=["game_date"])
    stats = pd.read_sql("select * from team_game_stats", engine)
    if games.empty:
        raise DataUnavailable("No completed games precede this matchup.")
    year = target.year if target.month >= 9 else target.year - 1
    row = {"game_id": game["game_id"], "game_date": target,
           "season": game.get("season", f"{year}-{(year + 1) % 100:02}"), "home_win": False,
           "home_team_id": game["home_team_id"], "away_team_id": game["away_team_id"]}
    games = pd.concat([games, pd.DataFrame([row])], ignore_index=True)
    additions = [{"game_id": game["game_id"], "team_id": game[f"{side}_team_id"],
                  "is_home": side == "home"} for side in ("home", "away")]
    stats = stats[stats.game_id.ne(game["game_id"])]
    stats = pd.concat([stats, pd.DataFrame(additions)], ignore_index=True)
    return games, stats


def predict(game, explain=True):
    bundle, metadata = load_models()["pregame_v1"]
    games, stats = matchup_frames(game)
    features = build_features(games, stats).set_index("game_id").loc[[game["game_id"]]]
    x = features[bundle["features"]]
    probability = calibrated(bundle, x)[0]
    elo = 1 / (1 + 10 ** (-(float(x.elo_diff.iloc[0]) + ELO_HOME) / 400))
    drivers = []
    if explain:
        contributions = bundle["model"].get_booster().predict(DMatrix(x), pred_contribs=True)[0]
        pairs = sorted(zip(x.columns, contributions[:-1]), key=lambda pair: -abs(pair[1]))
        drivers = [{"feature": key, "log_odds_impact": float(value)} for key, value in pairs[:4]]
    return {**game, "home_win_prob": float(probability), "elo_home_prob": elo,
            "model_version": metadata["model_version"], "drivers": drivers,
            "retrospective": game["status"] == "replay"}


def live_probability(game_id):
    if game_id.startswith("e"):
        try:
            game, plays = live_feed(game_id)
            game = named(game)
        except FEED_ERRORS as exc:
            raise DataUnavailable("The live play-by-play feed is unavailable.") from exc
    else:
        game = matchup(game_id)
        with SessionLocal() as session:
            rows = session.scalars(select(PbpEvent).where(PbpEvent.game_id == game_id)
                                   .order_by(PbpEvent.event_num)).all()
            plays = [{"period": row.period, "clock": row.clock, "home_score": row.home_score,
                      "away_score": row.away_score} for row in rows]
    curve = []
    if plays:
        frame = pd.DataFrame(plays)
        frame["clock_secs"] = clock_to_seconds(frame["clock"])
        frame = add_time_columns(frame.dropna(
            subset=["clock_secs", "home_score", "away_score"]).copy())
        frame = frame.sort_values("elapsed", kind="stable").drop_duplicates("elapsed", keep="last")
        if not frame.empty:
            source, stats = matchup_frames(game)
            features = build_features(source, stats).set_index("game_id")
            frame["elo_diff"] = features.loc[game_id, "elo_diff"]
            bundle, _ = load_models()["live_win_v1"]
            frame["home_win_prob"] = calibrated(bundle, make_features(frame))
            curve = frame[["elapsed", "home_score", "away_score", "home_win_prob"]
                          ].to_dict("records")
    return {**game, "points": curve, "home_win_prob": curve[-1]["home_win_prob"] if curve else None}


def find_players(query):
    matches = players.find_players_by_full_name(re.escape(query))
    return [{"id": p["id"], "name": p["full_name"]} for p in matches if p["is_active"]][:20]


def project(player_id, game_id):
    game = matchup(game_id)
    games, stats = matchup_frames(game)
    logs = pd.read_sql(select(PlayerGameLog).where(
        PlayerGameLog.player_id == player_id, PlayerGameLog.game_date < date.fromisoformat(game["game_date"]),
        PlayerGameLog.minutes > 0), engine, parse_dates=["game_date"])
    logs = logs.sort_values(["game_date", "game_id"])
    if len(logs) < 3:
        raise DataUnavailable("The player needs at least three prior appearances.")
    last = logs.iloc[-1]
    if last.team_id not in (game["home_team_id"], game["away_team_id"]):
        raise DataUnavailable("The player's latest logged team is outside this matchup.")
    target = {**last.to_dict(), "game_id": game_id, "game_date": pd.Timestamp(game["game_date"]),
              "is_home": last.team_id == game["home_team_id"], "minutes": 1.0}
    table = build_player_table(pd.concat([logs, pd.DataFrame([target])]), games, stats)
    row = table[table.game_id.eq(game_id)]
    bundle, meta = load_models()["player_props_v1"]
    if row.empty or not row.minutes_r10.iloc[0] >= meta["min_minutes_r10"]:
        raise DataUnavailable("The player lacks the recent minutes required by this model.")
    output = {}
    for stat in STATS:
        models = bundle[stat]
        mean, q10, q90 = (max(0.0, float(models[key].predict(row[meta["features"]])[0]))
                          for key in ("mean", "q10", "q90"))
        low, high = sorted([q10, q90])
        output[stat] = {"mean": round(mean, 1), "low": round(low, 1), "high": round(high, 1)}
    return {"player": last.player_name, "game_id": game_id, "stats": output,
            "retrospective": game["status"] == "replay", "model_version": meta["model_version"]}


def recent_form(team):
    matches = [key for key, item in NBA_TEAMS.items() if team.casefold() in
               (item["nickname"].casefold(), item["full_name"].casefold(), item["abbreviation"].casefold())]
    if not matches:
        raise DataUnavailable("Use an NBA team name or abbreviation.")
    team_id = matches[0]
    with SessionLocal() as session:
        games = session.scalars(select(Game).where(Game.home_win.is_not(None),
            (Game.home_team_id == team_id) | (Game.away_team_id == team_id)
        ).order_by(Game.game_date.desc(), Game.game_id.desc()).limit(5)).all()
    wins = sum(g.home_win == (g.home_team_id == team_id) for g in games)
    return {"team": NBA_TEAMS[team_id]["full_name"], "games": len(games),
            "wins": wins, "losses": len(games) - wins,
            "through": games[0].game_date.isoformat() if games else None}
