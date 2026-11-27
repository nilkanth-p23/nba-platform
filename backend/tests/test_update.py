from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import performance
from app.feed import EASTERN
from app.models import Base, Prediction
from pipelines import update


def test_forecasts_are_immutable_and_settle_only_after_final(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'monitoring.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(update, "SessionLocal", sessions)
    monkeypatch.setattr(performance, "SessionLocal", sessions)
    now = datetime.now(EASTERN)
    upcoming = now + timedelta(hours=1)
    game = {"game_id": "e123456", "game_date": now.date().isoformat(),
            "home_team_id": 1, "away_team_id": 2, "status": "scheduled",
            "starts_at": upcoming.isoformat(), "home_score": 0, "away_score": 0}
    started = {**game, "game_id": "e234567", "starts_at": (now - timedelta(hours=1)).isoformat()}
    monkeypatch.setattr(update, "schedule", lambda _day: [game, started])
    monkeypatch.setattr(update, "predict", lambda *_args, **_kw: {
        "model_version": "pregame_v1", "home_win_prob": 0.7, "elo_home_prob": 0.6})
    update.publish()
    monkeypatch.setattr(update, "predict", lambda *_args, **_kw: {
        "model_version": "pregame_v1", "home_win_prob": 0.2, "elo_home_prob": 0.4})
    update.publish()
    update.backfill()
    with sessions() as session:
        rows = session.scalars(select(Prediction).order_by(Prediction.model_version)).all()
        assert [(row.game_id, row.home_win_prob, row.outcome) for row in rows] == [
            ("e123456", 0.6, None), ("e123456", 0.7, None)]
    game.update(status="final", home_score=100, away_score=90)
    update.backfill()
    report = performance.performance()["models"][0]
    assert report["summary"]["count"] == 1
    assert report["summary"]["accuracy"] == 1
    assert report["elo"]["count"] == 1
    assert report["calibration"][0]["actual"] == 1
    engine.dispose()
