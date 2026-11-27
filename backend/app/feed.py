from datetime import datetime
from threading import Condition
from zoneinfo import ZoneInfo

import httpx
from cachetools import TTLCache, cached
from nba_api.stats.static import teams

EASTERN = ZoneInfo("America/New_York")
NBA_TEAMS = {item["id"]: item for item in teams.get_teams()}
BY_ABBR = {item["abbreviation"]: item["id"] for item in NBA_TEAMS.values()}
BY_ABBR.update({"GS": BY_ABBR["GSW"], "NY": BY_ABBR["NYK"], "NO": BY_ABBR["NOP"],
                "SA": BY_ABBR["SAS"], "UTAH": BY_ABBR["UTA"], "WSH": BY_ABBR["WAS"],
                "BRK": BY_ABBR["BKN"], "PHO": BY_ABBR["PHX"]})
ROOT = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
FEED_ERRORS = (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError)


def today():
    return datetime.now(EASTERN).date()


@cached(TTLCache(maxsize=128, ttl=12), condition=Condition())
def get_feed(path, parameter, value):
    response = httpx.get(f"{ROOT}/{path}", params={parameter: value}, timeout=6)
    response.raise_for_status()
    return response.json()


def from_event(event_id, competition):
    sides = {side["homeAway"]: side for side in competition["competitors"]}
    status = competition["status"]["type"]["state"]
    start = datetime.fromisoformat(competition["date"].replace("Z", "+00:00"))
    return {
        "game_id": f"e{event_id}", "game_date": start.astimezone(EASTERN).date().isoformat(),
        "starts_at": start.isoformat(), "status": {"pre": "scheduled", "in": "live",
                                                   "post": "final"}.get(status, status),
        "home_team_id": BY_ABBR[sides["home"]["team"]["abbreviation"]],
        "away_team_id": BY_ABBR[sides["away"]["team"]["abbreviation"]],
        "home_score": int(sides["home"].get("score") or 0),
        "away_score": int(sides["away"].get("score") or 0),
        "source": "ESPN scoreboard",
    }


def schedule(day):
    data = get_feed("scoreboard", "dates", day.strftime("%Y%m%d"))
    return [from_event(event["id"], event["competitions"][0]) for event in data["events"]]


def live_feed(game_id):
    data = get_feed("summary", "event", game_id[1:])
    item = from_event(game_id[1:], data["header"]["competitions"][0])
    plays = []
    for play in data.get("plays", []):
        clock = play["clock"]["displayValue"]
        minutes, seconds = clock.split(":") if ":" in clock else ("0", clock)
        plays.append({
            "period": play["period"]["number"], "clock": f"PT{minutes}M{seconds}S",
            "home_score": play.get("homeScore"), "away_score": play.get("awayScore"),
        })
    return item, plays
