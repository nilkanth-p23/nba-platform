const base = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type Game = {
  game_id: string; game_date: string; home: string; away: string; status: string;
  home_team_id: number; away_team_id: number;
  home_score: number | null; away_score: number | null; starts_at?: string; season?: string; source: string;
};
export type Driver = { feature: string; log_odds_impact: number };
type Point = { elapsed: number; home_win_prob: number };
type Metric = { count: number; accuracy: number; brier: number; log_loss: number };
type Report = {
  version: string; summary: Metric; elo: Metric | null; always_home: Metric;
  rolling: (Metric & { date: string; game_id: string })[];
  calibration: { predicted: number; actual: number; count: number }[];
};
export type Scoreboard = { date: string; games: Game[]; replays: Game[]; warning: string | null };
export type Prediction = Game & { home_win_prob: number; drivers: Driver[]; retrospective: boolean };
export type Live = Game & { points: Point[]; home_win_prob: number | null };
export type Player = { id: number; name: string; team_id?: number };
export type Projection = {
  player: string; retrospective: boolean;
  stats: Record<string, { mean: number; low: number; high: number }>;
};
export type Chat = { answer: string; evidence: { tool: string }[] };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(base + path, { cache: "no-store", ...init });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : `Request failed (${res.status}).`);
  }
  return res.json();
}

export const api = {
  games: (day?: string) => request<Scoreboard>(day ? `/games/today?day=${encodeURIComponent(day)}` : "/games/today"),
  seasons: () => request<{ seasons: string[] }>("/archive/seasons"),
  seasonGames: (season: string) => request<{ games: Game[] }>(`/archive/seasons/${encodeURIComponent(season)}/games`),
  matchup: (key: string) => request<Game>(`/matchups/${key}`),
  roster: (id: string) => request<Player[]>(`/games/${id}/players`),
  prediction: (id: string) => request<Prediction>(`/games/${id}/prediction`),
  live: (id: string) => request<Live>(`/games/${id}/live`),
  players: (query: string) => request<Player[]>(`/players?q=${encodeURIComponent(query)}`),
  project: (id: number, game: string) => request<Projection>(`/players/${id}/projection?game_id=${encodeURIComponent(game)}`),
  performance: () => request<{ models: Report[]; window_games: number }>("/model/performance"),
  chat: (question: string) => request<Chat>("/chat", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
  }),
};

export const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : "The request failed.";
