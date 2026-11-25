import time

import pandas as pd
from nba_api.stats.endpoints import playergamelogs

from app.db import SessionLocal
from app.models import PlayerGameLog
from pipelines.common import SEASONS, clean, insert_ignore, with_retries

COLUMNS = {
    "GAME_ID": "game_id", "PLAYER_ID": "player_id", "TEAM_ID": "team_id",
    "PLAYER_NAME": "player_name", "GAME_DATE": "game_date", "is_home": "is_home",
    "MIN": "minutes", "PTS": "pts", "REB": "reb", "AST": "ast", "FGM": "fgm",
    "FGA": "fga", "FG3M": "fg3m", "FTM": "ftm", "FTA": "fta", "TOV": "tov",
    "STL": "stl", "BLK": "blk",
}


def fetch_season(season):
    def call():
        return playergamelogs.PlayerGameLogs(
            season_nullable=season,
            season_type_nullable="Regular Season",
            timeout=60,
        ).get_data_frames()[0]

    return with_retries(call)


def build_rows(df):
    df = df.copy()
    df["is_home"] = df["MATCHUP"].str.contains("vs.", regex=False)
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"]).dt.date
    return df[list(COLUMNS)].rename(columns=COLUMNS)


def main():
    with SessionLocal() as session:
        for season in SEASONS:
            rows = build_rows(fetch_season(season))
            insert_ignore(session, PlayerGameLog,
                          clean(rows).to_dict("records"))
            print(f"{season}: {len(rows)} player rows")
            time.sleep(1)


if __name__ == "__main__":
    main()
