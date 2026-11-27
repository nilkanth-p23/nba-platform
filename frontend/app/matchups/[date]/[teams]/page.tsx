"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage, Game, Live, percent, Prediction } from "../../../../lib/api";
import { analystHref, gameDrivers, gameTime, playerHref, readableDate } from "../../../../lib/presentation";
import { Notice, TeamBadge } from "../../../components";

export default function MatchupPage() {
  const { date, teams } = useParams<{ date: string; teams: string }>();
  const [match, setMatch] = useState<Game>();
  const [forecast, setForecast] = useState<Prediction>();
  const [live, setLive] = useState<Live>();
  const [matchError, setMatchError] = useState("");
  const [forecastError, setForecastError] = useState("");
  const [liveError, setLiveError] = useState("");

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh(game: Game) {
      try {
        const state = await api.live(game.game_id);
        if (!active) return;
        setLive(state); setLiveError("");
        if (state.status === "live" || state.status === "scheduled") timer = setTimeout(() => void refresh(game), 12000);
      } catch (error) {
        if (!active) return;
        setLiveError(errorMessage(error));
        if (game.status === "live" || game.status === "scheduled") timer = setTimeout(() => void refresh(game), 12000);
      }
    }
    api.matchup(`${date}/${teams}`).then(game => {
      if (!active) return;
      setMatch(game);
      void refresh(game);
      api.prediction(game.game_id).then(value => { if (active) setForecast(value); })
        .catch(error => { if (active) setForecastError(errorMessage(error)); });
    }).catch(error => { if (active) setMatchError(errorMessage(error)); });
    return () => { active = false; clearTimeout(timer); };
  }, [date, teams]);

  const game = live ?? match;
  if (!game) return <><Link className="back-link" href="/#scoreboard">← Scoreboard</Link><Notice>{matchError || "Loading matchup…"}</Notice></>;
  const hasScore = game.status !== "scheduled";
  const replay = game.status === "replay" || game.status === "final";
  const points = live?.points ?? [];
  const drivers = gameDrivers(forecast?.drivers ?? []);

  return <>
    <Link className="back-link" href="/#scoreboard">← Scoreboard</Link>
    <section className="match-banner">
      <div className="match-meta"><span>{readableDate(game.game_date, true)}</span><span>{replay ? "Final · Replay" : game.status === "live" ? "Live" : gameTime(game.starts_at)}</span></div>
      <h1 className="sr-only">{game.away} at {game.home}</h1>
      <div className="match-line">
        <div><TeamBadge id={game.away_team_id} name={game.away} /><strong>{game.away}</strong><small>Away</small></div>
        <span className="match-score">{hasScore ? `${game.away_score} – ${game.home_score}` : "AT"}</span>
        <div><TeamBadge id={game.home_team_id} name={game.home} /><strong>{game.home}</strong><small>Home</small></div>
      </div>
      <div className="match-actions"><Link className="button primary" href={playerHref(game)}>Player projections <span aria-hidden="true">↗</span></Link><Link className="button on-dark" href={analystHref(game)}>Ask about this game <span aria-hidden="true">↗</span></Link></div>
    </section>
    <div className="detail-grid">
      <section className="panel forecast-panel">
        <h2>Before tipoff</h2><p className="muted">Estimated chance of winning before the game started.</p>
        {forecast ? <>
          <div className="split-numbers">
            <div><strong>{percent(1-forecast.home_win_prob)}</strong><span>{game.away}</span></div>
            <div><strong>{percent(forecast.home_win_prob)}</strong><span>{game.home}</span></div>
          </div>
          <div className="split-meter" aria-hidden="true"><span style={{ width: percent(1-forecast.home_win_prob) }} /></div>
          {replay && <small className="muted">Replay estimate based on pregame information.</small>}
          {!!drivers.length && <><h3>What shaped the forecast</h3>
            <ul className="drivers">{drivers.map(driver => <li key={driver.title}>
              <div><strong>{driver.title}</strong><small>{driver.explanation}</small></div>
              <span>Favors {game[driver.favors]}</span>
            </li>)}</ul>
          </>}
        </> : <Notice>{forecastError || "Loading forecast…"}</Notice>}
      </section>
      <section className="panel">
        <h2>{replay ? "How the game shifted" : "Win chance during the game"}</h2>
        <p className="muted">The line shows how the {game.home} win chance moved as the score and clock changed.</p>
        {points.length > 0 ? <>
          <div className="chart"><ResponsiveContainer>
            <LineChart data={points.map(p => ({ ...p, minute: +(p.elapsed / 60).toFixed(1) }))} margin={{ left: 2, right: 14, top: 8, bottom: 10 }}>
              <CartesianGrid stroke="#e8e1d8" vertical={false} />
              <XAxis dataKey="minute" type="number" tickCount={7} tickFormatter={m => `${m}m`} tick={{ fontSize: 12 }} />
              <YAxis domain={[0, 1]} tickFormatter={value => `${Math.round(value * 100)}%`} tick={{ fontSize: 12 }} width={46} />
              <Tooltip formatter={value => percent(Number(value))} labelFormatter={minute => `Minute ${minute}`} />
              <Line dataKey="home_win_prob" name={game.home} stroke="#c64a2b" dot={false} strokeWidth={3} />
            </LineChart>
          </ResponsiveContainer></div>
          {live?.home_win_prob != null && <p className="muted">Last plotted estimate: <strong>{percent(live.home_win_prob)}</strong> for {game.home}.</p>}
        </> : <Notice>{liveError || (game.status === "scheduled" ? "The chart appears when play starts." : live ? "Play-by-play is unavailable for this game." : "Loading play-by-play…")}</Notice>}
      </section>
    </div>
  </>;
}
