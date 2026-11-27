from collections import defaultdict
from math import log

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Game, Prediction


def metrics(rows):
    if not rows:
        return None
    p = [min(max(prob, 1e-6), 1 - 1e-6) for prob, _ in rows]
    y = [bool(outcome) for _, outcome in rows]
    return {"count": len(rows),
            "accuracy": sum((prob >= 0.5) == value for prob, value in zip(p, y)) / len(rows),
            "brier": sum((prob - value) ** 2 for prob, value in zip(p, y)) / len(rows),
            "log_loss": -sum(log(prob if value else 1 - prob) for prob, value in zip(p, y)) / len(rows)}


def performance():
    with SessionLocal() as session:
        rows = session.execute(select(Prediction, Game.game_date).join(
            Game, Game.game_id == Prediction.game_id).where(Prediction.outcome.is_not(None))
            .order_by(Game.game_date, Prediction.id)).all()
    models = defaultdict(list)
    elo = {}
    for row, day in rows:
        point = (day, row.home_win_prob, row.outcome, row.game_id)
        if row.model_version == "elo":
            elo[row.game_id] = point[1:3]
        else:
            models[row.model_version].append(point)
    results = []
    for version, points in models.items():
        pairs = [(p, y) for _, p, y, _ in points]
        bins = defaultdict(list)
        for p, y in pairs:
            bins[min(int(p * 10), 9)].append((p, y))
        rolling = []
        for index, point in enumerate(points):
            result = metrics(pairs[max(0, index - 29):index + 1])
            rolling.append({"date": point[0], "game_id": point[3], **result})
        results.append({"version": version, "summary": metrics(pairs),
                        "always_home": metrics([(1.0, y) for _, y in pairs]),
                        "elo": metrics([elo[gid] for *_, gid in points if gid in elo]),
                        "rolling": rolling[-180:],
                        "calibration": [{"predicted": sum(p for p, _ in values) / len(values),
                                         "actual": sum(y for _, y in values) / len(values),
                                         "count": len(values)} for _, values in sorted(bins.items())]})
    return {"models": results, "window_games": 30}
