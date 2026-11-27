import type { Driver, Game } from "./api";

const slug = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export const gameKey = (game: Game) => `${game.game_date}/${slug(`${game.away} at ${game.home}`)}`;
export const gameHref = (game: Game) => `/matchups/${gameKey(game)}`;
export const playerHref = (game: Game) => `/players?matchup=${encodeURIComponent(gameKey(game))}`;
export const analystHref = (game: Game) => `/analyst?matchup=${encodeURIComponent(gameKey(game))}`;

export function gameLabel(game: Game) {
  return `${game.away} at ${game.home}`;
}

export function readableDate(value: string, long = false) {
  return new Intl.DateTimeFormat("en-US", {
    weekday: long ? "long" : "short", month: long ? "long" : "short", day: "numeric", timeZone: "UTC",
  }).format(new Date(`${value}T12:00:00Z`));
}

export function gameTime(value?: string) {
  if (!value) return "Tipoff TBD";
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric", minute: "2-digit", timeZone: "America/New_York",
  }).format(new Date(value)) + " ET";
}

export const teamNames: Record<number, string> = {
  1610612737: "ATL", 1610612738: "BOS", 1610612739: "CLE", 1610612740: "NOP",
  1610612741: "CHI", 1610612742: "DAL", 1610612743: "DEN", 1610612744: "GSW",
  1610612745: "HOU", 1610612746: "LAC", 1610612747: "LAL", 1610612748: "MIA",
  1610612749: "MIL", 1610612750: "MIN", 1610612751: "BKN", 1610612752: "NYK",
  1610612753: "ORL", 1610612754: "IND", 1610612755: "PHI", 1610612756: "PHX",
  1610612757: "POR", 1610612758: "SAC", 1610612759: "SAS", 1610612760: "OKC",
  1610612761: "TOR", 1610612762: "UTA", 1610612763: "MEM", 1610612764: "WAS",
  1610612765: "DET", 1610612766: "CHA",
};

const drivers: Record<string, [string, string]> = {
  pts: ["Recent scoring", "How much each team has scored lately."],
  opp_pts: ["Recent defense", "How many points each team has allowed lately."],
  margin: ["Recent scoring margin", "How much each team has been outscoring its opponents."],
  efg: ["Shooting efficiency", "How well each team turns shots into points, giving three-pointers extra weight."],
  tov_rate: ["Ball security", "How often each team turns the ball over per possession."],
  reb_rate: ["Rebounding", "How often each team comes away with an available rebound."],
  poss: ["Game pace", "How many possessions each team typically plays."],
  net_rating: ["Two-way performance", "How much each team outscores opponents per 100 possessions."],
  win: ["Recent results", "How often each team has won lately."],
  season_win_pct: ["Season record", "Each team’s win percentage so far that season."],
  rest_days: ["Rest between games", "Time off since each team’s previous game."],
  back_to_back: ["Back-to-back games", "Whether either team played the previous day."],
  games_last_7: ["Schedule load", "How many games each team played in the previous week."],
  elo_diff: ["Team strength", "A rating that adjusts for past results and the strength of opponents."],
};

export function gameDrivers(items: Driver[]) {
  const shown = new Set<string>();
  return items.flatMap(item => {
    const feature = item.feature.replace(/^(diff|home|away)_/, "");
    const key = feature === "elo_diff" ? feature : feature.replace(/_r\d+$/, "");
    if (shown.has(key) || !drivers[key]) return [];
    shown.add(key);
    return [{ title: drivers[key][0], explanation: drivers[key][1],
      favors: item.log_odds_impact >= 0 ? "home" as const : "away" as const }];
  });
}

export function modelAnswer(text: string) {
  return text.replace(/\b(?:e\d{5,12}|00\d{8})\b/gi, "this matchup").replace(/\*\*(.*?)\*\*/g, "$1");
}
