"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage, Game, Player, Projection } from "../../lib/api";
import { gameKey, gameLabel, readableDate } from "../../lib/presentation";
import { Notice, PageTitle } from "../components";

const statNames: Record<string, string> = { pts: "Points", reb: "Rebounds", ast: "Assists" };

function Players() {
  const params = useSearchParams();
  const [key, setKey] = useState(params.get("matchup") || "");
  const [games, setGames] = useState<Game[]>([]);
  const [selected, setSelected] = useState<Game>();
  const [roster, setRoster] = useState<Player[]>([]);
  const [query, setQuery] = useState("");
  const [projection, setProjection] = useState<Projection>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [requesting, setRequesting] = useState(Boolean(params.get("matchup")));
  const resultHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (projection) resultHeading.current?.focus();
  }, [projection]);

  useEffect(() => {
    let active = true;
    api.games().then(board => { if (active) setGames([...board.games, ...board.replays]); })
      .catch(error => { if (active) setError(errorMessage(error)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    if (key) api.matchup(key).then(async game => {
      if (!active) return;
      setSelected(game);
      const players = await api.roster(game.game_id);
      if (!active) return;
      setRoster(players); setRequesting(false);
    }).catch(error => { if (active) { setError(errorMessage(error)); setRequesting(false); } });
    return () => { active = false; };
  }, [key]);

  const options = useMemo(() => selected && !games.some(game => gameKey(game) === gameKey(selected)) ? [selected, ...games] : games, [games, selected]);
  const filtered = roster.filter(player => player.name.toLowerCase().includes(query.trim().toLowerCase()));

  function choose(next: string) {
    setKey(next); setProjection(undefined); setRoster([]); setQuery(""); setError("");
    setSelected(undefined); setRequesting(Boolean(next));
  }

  async function showProjection(player: Player) {
    if (!selected) return;
    setError(""); setRequesting(true); setProjection(undefined);
    try { setProjection(await api.project(player.id, selected.game_id)); }
    catch (error) { setError(errorMessage(error)); }
    finally { setRequesting(false); }
  }

  return <>
    <PageTitle label="Player projections" title="How might they play?" description="Choose a matchup and player to see estimates for points, rebounds, and assists." />
    <div className="panel picker-panel">
      <label>Matchup<select value={key} onChange={event => choose(event.target.value)} disabled={requesting}>
        <option value="">{loading ? "Loading matchups…" : "Choose a matchup"}</option>
        {options.map(game => <option key={gameKey(game)} value={gameKey(game)}>{gameLabel(game)} · {readableDate(game.game_date)}</option>)}
      </select></label>
      {key && <label>Find a player<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by name" /></label>}
      {requesting && <p role="status">Loading player data…</p>}
      {!key && !loading && <p className="muted">Completed games are available to explore as replays.</p>}
      {key && !requesting && !filtered.length && !error && <Notice>{query ? "No players match your search." : "No recent player logs are available for these teams."}</Notice>}
      {!!filtered.length && <div className="roster">
        {[selected?.away_team_id, selected?.home_team_id].map((team, index) => {
          const members = filtered.filter(player => player.team_id === team);
          return members.length > 0 && <section key={team}><h2>{index === 0 ? selected?.away : selected?.home}</h2>
            <ul>{members.map(player => <li key={player.id}><button aria-pressed={projection?.player === player.name} disabled={requesting} onClick={() => void showProjection(player)}>{player.name}</button></li>)}</ul>
          </section>;
        })}
      </div>}
      {error && <p className="notice" role="alert">{error}</p>}
    </div>
    {projection && <section className="panel projection-panel" aria-live="polite">
      <p className="kicker">{projection.retrospective ? "Replay estimate" : "Pregame estimate"}</p><h2 ref={resultHeading} tabIndex={-1}>{projection.player}</h2>
      <div className="stat-grid">{Object.entries(projection.stats).map(([stat, value]) => <article key={stat}>
        <h3>{statNames[stat]}</h3><strong>{value.mean}</strong><span>Typical range: {value.low}–{value.high}</span>
      </article>)}</div>
      <p className="muted">The range spans the model’s 10th to 90th percentile. Estimates use past appearances and do not include injury or lineup news.</p>
    </section>}
  </>;
}

export default function Page() {
  return <Suspense fallback={<Notice>Loading player projections…</Notice>}><Players /></Suspense>;
}
