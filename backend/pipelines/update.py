import argparse

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.feed import today
from app.models import Game, PlayerGameLog, Prediction, TeamGameStats
from app.services import DataUnavailable, named, predict, schedule
from pipelines.common import clean, insert_ignore
from pipelines.ingest_games import build_rows as game_rows
from pipelines.ingest_games import fetch_season as fetch_games
from pipelines.ingest_player_logs import build_rows as player_rows
from pipelines.ingest_player_logs import fetch_season as fetch_players


def season_for(day):
    year = day.year if day.month >= 9 else day.year - 1
    return f"{year}-{(year + 1) % 100:02}"


def ingest():
    day = today()
    season = season_for(day)
    games, stats = game_rows(fetch_games(season), season)
    logs = player_rows(fetch_players(season))
    with SessionLocal() as session:
        insert_ignore(session, Game, clean(games).to_dict("records"))
        insert_ignore(session, TeamGameStats, clean(stats).to_dict("records"))
        insert_ignore(session, PlayerGameLog, clean(logs).to_dict("records"))
    print(f"Checked {len(games)} games and {len(logs)} player logs for {season}.")


def backfill():
    with SessionLocal() as session:
        dates = session.scalars(select(Game.game_date).join(
            Prediction, Prediction.game_id == Game.game_id
        ).where(Prediction.outcome.is_(None), Game.game_date <= today()).distinct()).all()
    for day in dates:
        games = schedule(day)
        with SessionLocal.begin() as session:
            for game in games:
                if game["status"] == "final" and game["home_score"] != game["away_score"]:
                    session.execute(update(Prediction).where(
                        Prediction.game_id == game["game_id"], Prediction.outcome.is_(None)
                    ).values(outcome=game["home_score"] > game["away_score"]))


def publish():
    from datetime import datetime

    from app.feed import EASTERN

    day = today()
    for game in schedule(day):
        starts = datetime.fromisoformat(game["starts_at"])
        if game["status"] != "scheduled" or starts <= datetime.now(EASTERN):
            continue
        try:
            prediction = predict(named(game), explain=False)
        except DataUnavailable as exc:
            print(f"Skipped {game['game_id']}: {exc}")
            continue
        with SessionLocal.begin() as session:
            if starts <= datetime.now(EASTERN):
                continue
            session.execute(insert(Game).values(
                game_id=game["game_id"], season=season_for(day), game_date=day,
                home_team_id=game["home_team_id"], away_team_id=game["away_team_id"],
            ).on_conflict_do_nothing())
            for version, probability in ((prediction["model_version"], prediction["home_win_prob"]),
                                         ("elo", prediction["elo_home_prob"])):
                session.execute(insert(Prediction).values(
                    game_id=game["game_id"], model_version=version, home_win_prob=probability,
                ).on_conflict_do_nothing())
        print(f"Checked forecasts for {game['game_id']}.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["daily", "ingest", "backfill", "publish"])
    step = parser.parse_args().step
    if step == "daily":
        ingest()
        backfill()
        publish()
    else:
        {"ingest": ingest, "backfill": backfill, "publish": publish}[step]()


if __name__ == "__main__":
    main()
