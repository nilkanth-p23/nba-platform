from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import services
from app.analyst import GameID, ask
from app.config import settings
from app.db import engine
from app.feed import today
from app.model_loader import load_models
from app.performance import performance


@asynccontextmanager
async def lifespan(_app):
    load_models()
    yield


app = FastAPI(title="NBA Prediction Platform", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[
    origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()],
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(services.DataUnavailable)
async def unavailable(_request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "database unavailable"})
    return {"status": "ok", "models": list(load_models()), "analyst_enabled": settings.analyst_enabled}


@app.get("/archive/seasons")
def archive_seasons():
    return services.archive_seasons()


@app.get("/archive/seasons/{season}/games")
def season_games(season: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}$")]):
    return services.season_games(season)


@app.get("/games/today")
def games(day: date | None = None):
    return services.game_list(day or today())


@app.get("/games/{game_id}/prediction")
def prediction(game_id: GameID):
    return services.predict(services.matchup(game_id))


@app.get("/games/{game_id}/live")
def live(game_id: GameID):
    return services.live_probability(game_id)


@app.get("/matchups/{day}/{slug}")
def named_matchup(day: date, slug: str):
    return services.resolve_matchup(day, slug)


@app.get("/games/{game_id}/players")
def matchup_players(game_id: GameID):
    return services.matchup_players(game_id)


@app.get("/players")
def players(q: Annotated[str, Query(min_length=2, max_length=80)]):
    return services.find_players(q)


@app.get("/players/{player_id}/projection")
def projection(player_id: int, game_id: GameID):
    return services.project(player_id, game_id)


@app.get("/model/performance")
def model_performance():
    return performance()


class ChatRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


@app.post("/chat")
@limiter.limit("5/minute")
def chat(request: Request, body: ChatRequest):
    return ask(body.question)
