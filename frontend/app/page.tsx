"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, Game, Prediction, Scoreboard } from "../lib/api";
import { gameDrivers, gameHref, gameTime, readableDate } from "../lib/presentation";
import { Notice, TeamBadge } from "./components";

function TeamRow({ name, id, score, home }: { name: string; id: number; score?: number | null; home?: boolean }) {
  return <div className="team-row"><TeamBadge id={id} name={name} /><strong>{name}{home && <small> Home</small>}</strong>{score != null && <b>{score}</b>}</div>;
}

function GameCard({ game }: { game: Game }) {
  const [prediction, setPrediction] = useState<Prediction>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    api.prediction(game.game_id).then(data => { if (active) setPrediction(data); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [game.game_id]);
  const home = prediction?.home_win_prob ?? .5;
  const reverse = home < .5;
  const displayScore = game.status !== "scheduled";
  const leaders = gameDrivers(prediction?.drivers ?? []);
  return <Link className="game-card" href={gameHref(game)}>
    <div className="card-top">
      <span className={`status ${game.status === "live" ? "status-live" : ""}`}>
        {game.status === "replay" ? "Final · Replay" : game.status === "final" ? "Final" : game.status === "live" ? "Live" : gameTime(game.starts_at)}
      </span>
      <span>{readableDate(game.game_date)}</span>
    </div>
    <TeamRow name={game.away} id={game.away_team_id} score={displayScore ? game.away_score : null} />
    <TeamRow name={game.home} id={game.home_team_id} home score={displayScore ? game.home_score : null} />
    <div className="card-forecast">
      {prediction ? <>
        <div className="forecast-label"><span>{reverse ? game.away : game.home} {home === .5 ? "win chance" : "favored"}</span><strong>{Math.round(Math.max(home, 1 - home) * 100)}%</strong></div>
        <div className="meter" aria-hidden="true"><span style={{ width: `${Math.max(home, 1-home) * 100}%` }} /></div>
        <small>Pregame estimate{leaders[0] ? ` · ${leaders[0].title}` : ""}</small>
      </> : <small>{failed ? "Pregame estimate unavailable" : "Loading pregame estimate…"}</small>}
    </div>
    <span className="card-link">{game.status === "replay" || game.status === "final" ? "Explore replay" : "See matchup"} <span aria-hidden="true">↗</span></span>
  </Link>;
}

function shiftDate(date: string, days: number) {
  const value = new Date(`${date}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

export default function Home() {
  const [date, setDate] = useState("");
  const [board, setBoard] = useState<Scoreboard>();
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.games(date || undefined).then(value => { if (active) setBoard(value); })
      .catch(err => { if (active) setError(errorMessage(err)); });
    return () => { active = false; };
  }, [date]);
  const shownDate = date || board?.date || "";
  function choose(day: string) {
    if (day === date) return;
    setBoard(undefined);
    setError("");
    setDate(day);
  }
  return <>
    <section className="hero">
      <div className="hero-content">
        <p className="kicker">NBA prediction model analysis</p>
        <h1>See the game<br />behind the score.</h1>
        <p>Pick a matchup to see who’s favored, what shaped the forecast, and how players are projected to perform.</p>
        <div className="hero-actions"><a href="#scoreboard" className="button primary">Explore games <span aria-hidden="true">↓</span></a><Link className="button on-dark" href="/analyst">Ask the analyst <span aria-hidden="true">↗</span></Link></div>
      </div>
    </section>
    <section className="scoreboard" id="scoreboard" aria-labelledby="scoreboard-title">
      <div className="section-head">
        <div><h2 id="scoreboard-title">Scoreboard</h2><p>{shownDate ? readableDate(shownDate, true) : "NBA games"} · Eastern time</p></div>
        <div className="date-controls">
          <button type="button" aria-label="Previous day" disabled={!shownDate} onClick={() => choose(shiftDate(shownDate, -1))}>‹</button>
          <label className="date-label"><span className="sr-only">Choose game date</span><input type="date" value={shownDate} onChange={e => choose(e.target.value)} /></label>
          <button type="button" aria-label="Next day" disabled={!shownDate} onClick={() => choose(shiftDate(shownDate, 1))}>›</button>
          <button type="button" className="today-control" onClick={() => choose("")}>Today</button>
        </div>
      </div>
      {error && <Notice>{error}</Notice>}
      {!board && !error && <div className="grid loading-grid" role="status"><span className="sr-only">Loading games</span><div /><div /><div /></div>}
      {board && <>
        {board.warning && <Notice>The latest schedule is temporarily unavailable. Replays below are still available.</Notice>}
        {board.games.length > 0 && <div className="grid">{board.games.map(g => <GameCard key={g.game_id} game={g} />)}</div>}
        {!board.games.length && !board.warning && !board.replays.some(g => g.game_date === board.date) && <Notice>No games on this date. Use the arrows to change dates or pick a replay below.</Notice>}
        {!!board.replays.length && <section className="archive">
          <div className="section-head"><div><h2>{board.games.length ? "Recent replays" : "Game replays"}</h2><p>Pick a completed game to follow how the win chances changed.</p></div></div>
          <div className="grid">{board.replays.map(g => <GameCard key={g.game_id} game={g} />)}</div>
        </section>}
      </>}
    </section>
    <section className="method-strip">
      <div><p className="kicker">About the project</p><h2>Built to explain the forecast.</h2><p>See how the models use team form, scoring, and the game clock, and how their estimates hold up on real outcomes.</p></div>
      <Link className="button secondary" href="/performance">Explore model results <span aria-hidden="true">↗</span></Link>
    </section>
  </>;
}
