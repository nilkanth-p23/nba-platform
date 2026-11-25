import time

import pandas as pd
from nba_api.stats.endpoints import leaguegamefinder

from app.db import SessionLocal
from app.models import Game, TeamGameStats
from pipelines.common import SEASONS, clean, insert_ignore, with_retries

STAT_COLS = ["PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA",
             "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF"]


def fetch_season(season):
    def call():
        return leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            league_id_nullable="00",
            season_type_nullable="Regular Season",
            timeout=60,
        ).get_data_frames()[0]

    return with_retries(call)


def build_rows(df, season):
    df = df.copy()
    df["is_home"] = df["MATCHUP"].str.contains("vs.", regex=False)
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"]).dt.date

    team_stats = df[["GAME_ID", "TEAM_ID", "is_home"] +
                    STAT_COLS].rename(columns=str.lower)

    home = df[df["is_home"]][["GAME_ID", "GAME_DATE", "TEAM_ID", "PTS"]].rename(
        columns={"TEAM_ID": "home_team_id", "PTS": "home_pts"}
    )
    away = df[~df["is_home"]][["GAME_ID", "TEAM_ID", "PTS"]].rename(
        columns={"TEAM_ID": "away_team_id", "PTS": "away_pts"}
    )
    games = home.merge(away, on="GAME_ID")
    games["home_win"] = games.apply(
        lambda r: None if pd.isna(r.home_pts) or pd.isna(r.away_pts)
        else bool(r.home_pts > r.away_pts),
        axis=1,
    )
    games["season"] = season
    games = games.rename(
        columns={"GAME_ID": "game_id", "GAME_DATE": "game_date"})
    return games, team_stats


def main():
    with SessionLocal() as session:
        for season in SEASONS:
            df = fetch_season(season)
            games, team_stats = build_rows(df, season)
            insert_ignore(session, Game, clean(games).to_dict("records"))
            insert_ignore(session, TeamGameStats, clean(
                team_stats).to_dict("records"))
            print(f"{season}: {len(games)} games")
            time.sleep(1)


if __name__ == "__main__":
    main()
