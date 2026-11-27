"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage, Live, percent, Prediction } from "../../../lib/api";

export default function GamePage() {
  const { id } = useParams<{ id: string }>();
  const [prediction, setPrediction] = useState<Prediction>();
  const [live, setLive] = useState<Live>();
  const [error, setError] = useState("");
  const [predictionError, setPredictionError] = useState("");
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    api.prediction(id).then(value => { if (active) setPrediction(value); })
      .catch(err => { if (active) setPredictionError(errorMessage(err)); });
    async function refresh() {
      try {
        const value = await api.live(id);
        if (!active) return;
        setLive(value); setError("");
        if (value.status === "live" || value.status === "scheduled") timer = setTimeout(refresh, 12000);
      } catch (err) {
        if (!active) return;
        setError(errorMessage(err));
        if (id.startsWith("e")) timer = setTimeout(refresh, 12000);
      }
    }
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [id]);
  const game = live ?? prediction;
  return <>
    <p><Link href="/">← Scoreboard</Link></p>
    <h1>{game ? `${game.away} at ${game.home}` : "Game analysis"}</h1>
    {game && <p className="muted">{game.status} · {game.game_date} · Game {id} · {game.source}</p>}
    {error && <p role="alert">{error}</p>}
    {predictionError && <p role="alert">{predictionError}</p>}
    {!game && !error && <p role="status">Loading game…</p>}
    {game && <div className="panel">
      {game.status !== "scheduled" && <p className="score">{game.away_score} <span>–</span> {game.home_score}</p>}
      <h2>{game.status === "replay" ? "Replay win probability" : "In-game win probability"}</h2>
      {live?.points.length ? <>
        <p>{percent(live.home_win_prob ?? 0)} home-win probability at the latest plotted state</p>
        <div className="chart"><ResponsiveContainer>
          <LineChart data={live.points.map(p => ({ ...p, minute: +(p.elapsed / 60).toFixed(1) }))}>
            <CartesianGrid stroke="#253b38" /><XAxis dataKey="minute" type="number" tickCount={9} />
            <YAxis domain={[0, 1]} tickFormatter={percent} />
            <Tooltip formatter={value => percent(Number(value))} labelFormatter={value => `Minute ${value}`} />
            <Line dataKey="home_win_prob" name="Home win" stroke="#a6f180" dot={false} strokeWidth={3} />
          </LineChart>
        </ResponsiveContainer></div>
      </> : <p className="muted">Play-by-play is unavailable for this game state.</p>}
    </div>}
    {prediction && <section className="panel">
      <h2>Pregame model {prediction.retrospective ? "· retrospective" : ""}</h2>
      <p><strong>{percent(prediction.home_win_prob)}</strong> home-win probability</p>
      <ul>{prediction.drivers.map(d => <li key={d.feature}>{d.feature.replaceAll("_", " ")} · {d.log_odds_impact > 0 ? "+" : ""}{d.log_odds_impact.toFixed(2)} raw log-odds</li>)}</ul>
      <Link href={`/players?game=${id}`}>Explore player projections →</Link>
    </section>}
  </>;
}
