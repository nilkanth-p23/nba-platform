from datetime import date

import pandas as pd
from fastapi.testclient import TestClient

from app import analyst, main, services
from app.performance import metrics
from ml.features import build_features


def test_feature_shift_excludes_target_result():
    games = pd.DataFrame([{"game_id": str(i), "season": "2025-26",
                           "game_date": pd.Timestamp(2025, 11, i + 1),
                           "home_win": True, "home_team_id": 1, "away_team_id": 2}
                          for i in range(5)])
    stats = pd.DataFrame([{"game_id": str(i), "team_id": team, "is_home": team == 1,
                           "pts": 100 + team, "fgm": 30, "fga": 80, "fg3m": 10, "fta": 18,
                           "ftm": 15, "oreb": 8, "reb": 44, "tov": 12}
                          for i in range(5) for team in (1, 2)])
    before = build_features(games, stats).set_index("game_id").loc["3"].drop("home_win")
    stats.loc[stats.game_id == "3", "pts"] = 999
    games.loc[games.game_id == "3", "home_win"] = False
    after = build_features(games, stats).set_index("game_id").loc["3"].drop("home_win")
    pd.testing.assert_series_equal(before, after)


def test_health(monkeypatch):
    from sqlalchemy import create_engine

    monkeypatch.setattr(main, "engine", create_engine("sqlite://"))
    with TestClient(main.app) as client:
        result = client.get("/health")
    assert result.status_code == 200
    assert "live_win_v1" in result.json()["models"]


def test_routes_and_validation(monkeypatch):
    game_id = "0022600001"
    monkeypatch.setattr(services, "game_list", lambda day: {"date": day})
    monkeypatch.setattr(services, "matchup", lambda gid: {"game_id": gid})
    monkeypatch.setattr(services, "predict", lambda game: {**game, "home_win_prob": 0.6})
    monkeypatch.setattr(services, "live_probability", lambda gid: {"game_id": gid, "points": []})
    monkeypatch.setattr(services, "find_players", lambda query: [{"id": 1, "name": query}])
    monkeypatch.setattr(services, "project", lambda pid, gid: {"player_id": pid, "game_id": gid})
    monkeypatch.setattr(main, "performance", lambda: {"models": []})
    monkeypatch.setattr(main, "ask", lambda question: {"answer": question})
    client = TestClient(main.app)
    assert client.get("/games/today?day=2026-11-26").json()["date"] == "2026-11-26"
    assert client.get(f"/games/{game_id}/prediction").json()["home_win_prob"] == 0.6
    assert client.get(f"/games/{game_id}/live").json()["points"] == []
    assert client.get("/games/invalid/live").status_code == 422
    assert client.get("/players?q=James").json()[0]["name"] == "James"
    assert client.get(f"/players/1/projection?game_id={game_id}").json()["player_id"] == 1
    assert client.get("/model/performance").json() == {"models": []}
    assert client.post("/chat", json={"question": "  "}).status_code == 422
    assert client.post("/chat", json={"question": "How?"}).json()["answer"] == "How?"


def test_grounded_ollama_loop(monkeypatch):
    calls = [{"function": {"name": "get_team_recent_form", "arguments": {"team": "BOS"}}}]
    messages = iter([{"tool_calls": calls}, {"content": "Boston won 4 of its last 5."}])
    monkeypatch.setitem(analyst.TOOLS, "get_team_recent_form",
                        (analyst.TeamInput, lambda team: {"wins": 4, "games": 5}, ""))
    seen = []

    def post(_self, _url, json):
        import httpx

        seen.append(list(json["messages"]))
        return httpx.Response(200, json={"message": next(messages)},
                              request=httpx.Request("POST", "http://ollama.local"))

    monkeypatch.setattr(analyst.httpx.Client, "post", post)
    result = analyst.ask("How are the Celtics doing?")
    assert result["evidence"][0]["result"]["wins"] == 4
    assert seen[1][-1]["role"] == "tool"
    assert result["answer"] == "Boston won 4 of its last 5."
    assert "error" in analyst.run_tool("get_win_probability", {"game_id": "../"})
    assert "error" in analyst.run_tool("invented_tool", {})


def test_metrics():
    result = metrics([(0.75, True), (0.25, False)])
    assert result["accuracy"] == 1
    assert result["brier"] == 0.0625
    assert metrics([]) is None


def test_all_analyst_tools(monkeypatch):
    monkeypatch.setattr(services, "game_list", lambda day: {"date": date(2026, 11, 26)})
    monkeypatch.setattr(services, "matchup", lambda gid: {"game_id": gid})
    monkeypatch.setattr(services, "predict", lambda game: {**game, "home_win_prob": 0.6})
    monkeypatch.setattr(services, "live_probability", lambda gid: {"game_id": gid, "points": [1]})
    monkeypatch.setattr(services, "find_players", lambda name: [{"id": 42, "name": name}])
    monkeypatch.setattr(services, "project", lambda pid, gid: {"id": pid, "game_id": gid})
    monkeypatch.setitem(analyst.TOOLS, "get_team_recent_form",
                        (analyst.TeamInput, lambda team: {"team": team}, ""))
    game = {"game_id": "0022600001"}
    assert analyst.run_tool("get_todays_games", {})["date"] == date(2026, 11, 26)
    assert analyst.run_tool("get_win_probability", game)["home_win_prob"] == 0.6
    assert "points" not in analyst.run_tool("get_live_probability", game)
    assert analyst.run_tool("get_player_projection", {**game, "player_name": "A Player"})["id"] == 42
    assert analyst.run_tool("get_prediction_drivers", game)["home_win_prob"] == 0.6
    assert analyst.run_tool("get_team_recent_form", {"team": "BOS"})["team"] == "BOS"
