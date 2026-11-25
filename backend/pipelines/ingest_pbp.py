import argparse
import time
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import playbyplayv3
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Game, PbpEvent
from pipelines.common import clean, insert_ignore, with_retries

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "pbp"


def fetch_game(game_id):
    path = RAW_DIR / f"{game_id}.csv"
    if path.exists():
        return pd.read_csv(path, dtype=str, keep_default_na=False)

    def call():
        return playbyplayv3.PlayByPlayV3(game_id=game_id, timeout=60).get_data_frames()[0]

    df = with_retries(call)
    df.to_csv(path, index=False)
    return df


def parse(df, game_id):
    out = pd.DataFrame({
        "game_id": game_id,
        "event_num": pd.to_numeric(df["actionNumber"], errors="coerce"),
        "period": pd.to_numeric(df["period"], errors="coerce"),
        "clock": df["clock"].astype(str),
        "home_score": pd.to_numeric(df["scoreHome"], errors="coerce"),
        "away_score": pd.to_numeric(df["scoreAway"], errors="coerce"),
        "description": df["description"].astype(str),
    })
    out = out.dropna(subset=["event_num", "period"])
    out = out.sort_values("event_num").drop_duplicates("event_num")
    out[["home_score", "away_score"]] = out[[
        "home_score", "away_score"]].ffill().fillna(0)
    int_cols = ["event_num", "period", "home_score", "away_score"]
    out[int_cols] = out[int_cols].astype(int)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as session:
        done = set(session.scalars(select(PbpEvent.game_id).distinct()))
        game_ids = session.scalars(
            select(Game.game_id).where(
                Game.home_win.is_not(None)).order_by(Game.game_date)
        ).all()
        todo = [g for g in game_ids if g not in done]
        if args.limit:
            todo = todo[: args.limit]
        print(f"{len(todo)} games to fetch")

        for i, game_id in enumerate(todo, 1):
            try:
                rows = clean(parse(fetch_game(game_id), game_id)
                             ).to_dict("records")
                insert_ignore(session, PbpEvent, rows)
            except Exception as exc:
                session.rollback()
                print(f"skip {game_id}: {exc}")
            if i % 50 == 0:
                print(f"{i}/{len(todo)}")
            time.sleep(1)


if __name__ == "__main__":
    main()
