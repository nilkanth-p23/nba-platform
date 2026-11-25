from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"
    game_id: Mapped[str] = mapped_column(String, primary_key=True)
    season: Mapped[str] = mapped_column(String, index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    home_team_id: Mapped[int] = mapped_column(Integer)
    away_team_id: Mapped[int] = mapped_column(Integer)
    home_pts: Mapped[int | None] = mapped_column(Integer)
    away_pts: Mapped[int | None] = mapped_column(Integer)
    home_win: Mapped[bool | None] = mapped_column(Boolean)


class TeamGameStats(Base):
    __tablename__ = "team_game_stats"
    game_id: Mapped[str] = mapped_column(String, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_home: Mapped[bool] = mapped_column(Boolean)
    pts: Mapped[int | None] = mapped_column(Integer)
    fgm: Mapped[int | None] = mapped_column(Integer)
    fga: Mapped[int | None] = mapped_column(Integer)
    fg3m: Mapped[int | None] = mapped_column(Integer)
    fg3a: Mapped[int | None] = mapped_column(Integer)
    ftm: Mapped[int | None] = mapped_column(Integer)
    fta: Mapped[int | None] = mapped_column(Integer)
    oreb: Mapped[int | None] = mapped_column(Integer)
    dreb: Mapped[int | None] = mapped_column(Integer)
    reb: Mapped[int | None] = mapped_column(Integer)
    ast: Mapped[int | None] = mapped_column(Integer)
    stl: Mapped[int | None] = mapped_column(Integer)
    blk: Mapped[int | None] = mapped_column(Integer)
    tov: Mapped[int | None] = mapped_column(Integer)
    pf: Mapped[int | None] = mapped_column(Integer)


class PlayerGameLog(Base):
    __tablename__ = "player_game_logs"
    game_id: Mapped[str] = mapped_column(String, primary_key=True)
    player_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer)
    player_name: Mapped[str] = mapped_column(String)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    is_home: Mapped[bool | None] = mapped_column(Boolean)
    minutes: Mapped[float | None] = mapped_column(Float)
    pts: Mapped[int | None] = mapped_column(Integer)
    reb: Mapped[int | None] = mapped_column(Integer)
    ast: Mapped[int | None] = mapped_column(Integer)
    fgm: Mapped[int | None] = mapped_column(Integer)
    fga: Mapped[int | None] = mapped_column(Integer)
    fg3m: Mapped[int | None] = mapped_column(Integer)
    ftm: Mapped[int | None] = mapped_column(Integer)
    fta: Mapped[int | None] = mapped_column(Integer)
    tov: Mapped[int | None] = mapped_column(Integer)
    stl: Mapped[int | None] = mapped_column(Integer)
    blk: Mapped[int | None] = mapped_column(Integer)


class PbpEvent(Base):
    __tablename__ = "pbp_events"
    game_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_num: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[int] = mapped_column(Integer)
    clock: Mapped[str | None] = mapped_column(String)
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(String)


class GameFeatures(Base):
    __tablename__ = "game_features"
    game_id: Mapped[str] = mapped_column(String, primary_key=True)
    features: Mapped[dict] = mapped_column(JSON)
    home_win: Mapped[bool | None] = mapped_column(Boolean)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("game_id", "model_version"),)
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String, index=True)
    model_version: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now())
    home_win_prob: Mapped[float] = mapped_column(Float)
    outcome: Mapped[bool | None] = mapped_column(Boolean)
