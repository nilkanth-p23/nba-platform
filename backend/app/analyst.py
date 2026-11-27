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


def request_turn(client, messages):
    if settings.analyst_provider == "workers_ai":
        account = settings.cloudflare_account_id
        token = settings.cloudflare_ai_token.get_secret_value()
        response = client.post(
            f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": settings.workers_ai_model, "messages": messages, "tools": SCHEMAS,
                  "stream": False, "max_tokens": 450, "temperature": 0},
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]

    response = client.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json={
        "model": settings.ollama_model, "stream": False, "think": False,
        "messages": messages, "tools": SCHEMAS,
        "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 350, "num_thread": 4},
    })
    response.raise_for_status()
    return response.json()["message"]


def ask(question):
    if not settings.analyst_enabled:
        raise services.DataUnavailable("The analyst is disabled on this deployment.")
    system = ("You are an NBA analyst. Always call a tool before making a factual claim. "
              "Use only tool results. Quote exact numbers, distinguish replay from live, "
              "and say if data is unavailable. Never invent a game ID. "
              "A probability of 0.62 means 62%. Mention teams and dates instead of game IDs. "
              "Translate feature names into plain basketball language. Keep answers brief.")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    evidence = []
    hosted = settings.analyst_provider == "workers_ai"
    try:
        with httpx.Client(timeout=httpx.Timeout(60 if hosted else 45, connect=6)) as client:
            for _ in range(4 if hosted else 5):
                message = request_turn(client, messages)
                calls = (message.get("tool_calls") or [])[:3]
                content = message.get("content") or ""
                if not calls:
                    if evidence and content.strip():
                        return {"answer": content, "evidence": evidence}
                    break
                if hosted:
                    messages.append({"role": "assistant", "content": content or None,
                                     "tool_calls": calls})
                else:
                    messages.append({**message, "tool_calls": calls})
                for call in calls:
                    function = call["function"]
                    name = function["name"]
                    raw = function.get("arguments", {})
                    try:
                        arguments = json.loads(raw) if isinstance(raw, str) else raw
                    except json.JSONDecodeError:
                        arguments = None
                    result = run_tool(name, arguments)
                    evidence.append({"tool": name, "arguments": arguments, "result": result})
                    tool_response = {"role": "tool", "content": json.dumps(result, default=str)}
                    if hosted:
                        tool_response["tool_call_id"] = call["id"]
                    else:
                        tool_response["tool_name"] = name
                    messages.append(tool_response)
    except httpx.HTTPStatusError as exc:
        if hosted:
            return {"answer": "The hosted analyst is temporarily unavailable. The game and player pages still show the underlying estimates.",
                    "evidence": evidence}
        raise services.DataUnavailable("Ollama is unavailable.") from exc
    except (httpx.HTTPError, KeyError, ValueError, TypeError, IndexError) as exc:
        provider = "The hosted analyst" if hosted else "Ollama"
        raise services.DataUnavailable(f"{provider} is unavailable or returned an invalid response.") from exc
    return {"answer": "I couldn't verify an answer. Try a team abbreviation or a game ID.",
            "evidence": evidence}
