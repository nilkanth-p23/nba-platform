"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, Game, percent, Prediction, Scoreboard } from "../lib/api";

function Card({ game }: { game: Game }) {
  const [prediction, setPrediction] = useState<Prediction>();
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.prediction(game.game_id).then(value => { if (active) setPrediction(value); })
      .catch(err => { if (active) setError(errorMessage(err)); });
    return () => { active = false; };
  }, [game.game_id]);
  return <article className="panel">
    <div className="eyebrow">{game.status} · {game.game_date}</div>
    <h3>{game.away} <span className="muted">at</span> {game.home}</h3>
    {game.status !== "scheduled" && <p className="score">{game.away_score} <span>–</span> {game.home_score}</p>}
    {prediction ? <>
      <p><strong>{percent(prediction.home_win_prob)}</strong> home-win probability</p>
      <p className="muted">{prediction.drivers.slice(0, 2).map(d => d.feature.replaceAll("_", " ")).join(" · ")}</p>
    </> : <p className="muted">{error || "Loading estimate…"}</p>}
    <Link href={`/games/${game.game_id}`}>View game →</Link>
  </article>;
}

export default function Home() {
  const [day, setDay] = useState("");
  const [scoreboard, setScoreboard] = useState<Scoreboard>();
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.games(day || undefined).then(value => { if (active) setScoreboard(value); })
      .catch(err => { if (active) setError(errorMessage(err)); });
    return () => { active = false; };
  }, [day]);
  return <>
    <section className="hero">
      <div className="eyebrow">NBA game analysis</div>
      <h1>The game, in probabilities.</h1>
      <p>Explore pregame estimates, live win probability, and historical replays.</p>
    </section>
    <div className="section-head"><h2>Scoreboard</h2>
      <label>Game date <input type="date" value={day || scoreboard?.date || ""} onChange={e => {
        setScoreboard(undefined); setError(""); setDay(e.target.value);
      }} /></label>
    </div>
    {error && <p role="alert">{error}</p>}
    {!scoreboard && !error && <p role="status">Loading games…</p>}
    {scoreboard && <>
      {scoreboard.warning && <p role="status">{scoreboard.warning}</p>}
      {scoreboard.games.length ? <div className="grid">{scoreboard.games.map(g => <Card key={g.game_id} game={g} />)}</div>
        : <p className="muted">No scheduled games shown for this date.</p>}
      {!!scoreboard.replays.length && <><h2>From the archive</h2><div className="grid">
        {scoreboard.replays.map(g => <Card key={g.game_id} game={g} />)}
      </div></>}
    </>}
  </>;
}
