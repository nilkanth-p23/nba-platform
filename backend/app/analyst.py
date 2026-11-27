import json
from typing import Annotated

import httpx
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from app import services
from app.config import settings
from app.feed import today

GameID = Annotated[str, StringConstraints(pattern=r"^(?:[0-9]{10}|e[0-9]{5,12})$")]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GameInput(Empty):
    game_id: GameID


class PlayerInput(GameInput):
    player_name: ShortText


class TeamInput(Empty):
    team: ShortText


def win_probability(game_id):
    return services.predict(services.matchup(game_id))


def live_probability(game_id):
    result = services.live_probability(game_id)
    return {key: value for key, value in result.items() if key != "points"}


def projection(game_id, player_name):
    matches = services.find_players(player_name)
    if len(matches) != 1:
        raise services.DataUnavailable("Specify one player's full name.")
    return services.project(matches[0]["id"], game_id)


TOOLS = {
    "get_todays_games": (Empty, lambda: services.game_list(today()),
                         "Find today's matchups or historical replay IDs."),
    "get_win_probability": (GameInput, win_probability, "Get pregame probability and drivers."),
    "get_live_probability": (GameInput, live_probability, "Get latest in-game probability and score."),
    "get_player_projection": (PlayerInput, projection, "Get a player projection for a game."),
    "get_prediction_drivers": (GameInput, win_probability, "Get pregame SHAP drivers."),
    "get_team_recent_form": (TeamInput, services.recent_form, "Get a team's last five results."),
}
SCHEMAS = [{"type": "function", "function": {"name": name, "description": description,
            "parameters": schema.model_json_schema()}}
           for name, (schema, _, description) in TOOLS.items()]


def run_tool(name, arguments):
    if name not in TOOLS:
        return {"error": "Unknown tool."}
    schema, call, _ = TOOLS[name]
    try:
        return call(**schema.model_validate(arguments).model_dump())
    except ValidationError:
        return {"error": "Invalid tool arguments."}
    except services.DataUnavailable as exc:
        return {"error": str(exc)}


def ask(question):
    if not settings.analyst_enabled:
        raise services.DataUnavailable("The analyst runs in the local edition of this app.")
    system = ("You are an NBA analyst. Always call a tool before making a factual claim. "
              "Use only tool results. Quote exact numbers, distinguish replay from live, "
              "and say if data is unavailable. Never invent a game ID. "
              "A probability of 0.62 means 62%. Keep answers brief. Educational use only.")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    evidence = []
    try:
        with httpx.Client(timeout=45) as client:
            for _ in range(5):
                response = client.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json={
                    "model": settings.ollama_model, "stream": False, "think": False,
                    "messages": messages, "tools": SCHEMAS,
                    "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 350, "num_thread": 4},
                })
                response.raise_for_status()
                message = response.json()["message"]
                calls = message.get("tool_calls") or []
                if not calls:
                    if evidence and message.get("content", "").strip():
                        return {"answer": message["content"], "evidence": evidence}
                    break
                messages.append(message)
                for call in calls[:3]:
                    function = call["function"]
                    name = function["name"]
                    result = run_tool(name, function.get("arguments", {}))
                    evidence.append({"tool": name, "arguments": function.get("arguments", {}), "result": result})
                    messages.append({"role": "tool", "tool_name": name,
                                     "content": json.dumps(result, default=str)})
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise services.DataUnavailable("Ollama is unavailable or returned an invalid response.") from exc
    return {"answer": "I couldn't verify an answer. Try a team abbreviation or a game ID.",
            "evidence": evidence}
