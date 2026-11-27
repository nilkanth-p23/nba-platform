"use client";

import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";
import { api, errorMessage, Player, Projection } from "../../lib/api";

function Players() {
  const params = useSearchParams();
  const [game, setGame] = useState(params.get("game") ?? "");
  const [query, setQuery] = useState("");
  const [players, setPlayers] = useState<Player[]>([]);
  const [projection, setProjection] = useState<Projection>();
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  async function search(event: FormEvent) {
    event.preventDefault(); setStatus("Searching…"); setBusy(true); setProjection(undefined); setPlayers([]);
    try {
      const results = await api.players(query.trim());
      setPlayers(results); setStatus(results.length ? "" : "No matching active players.");
    } catch (err) { setStatus(errorMessage(err)); }
    finally { setBusy(false); }
  }
  async function project(player: Player) {
    if (!game.trim()) { setStatus("Enter the game ID shown on a game page."); return; }
    setStatus("Calculating projection…"); setBusy(true); setProjection(undefined);
    try { setProjection(await api.project(player.id, game.trim())); setStatus(""); }
    catch (err) { setStatus(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <><h1>Player projections</h1>
    <form className="panel form" onSubmit={search}>
      <label>Game ID<input value={game} onChange={e => { setGame(e.target.value); setProjection(undefined); }} placeholder="From a game page" /></label>
      <label>Player name<input value={query} onChange={e => setQuery(e.target.value)} minLength={2} required /></label>
      <button disabled={busy}>Search</button>
    </form>
    <p role="status">{status}</p>
    <ul className="players">{players.map(p => <li key={p.id}><button disabled={busy} onClick={() => void project(p)}>{p.name}</button></li>)}</ul>
    {projection && <div className="panel"><h2>{projection.player}</h2>
      <p className="muted">{projection.retrospective ? "Retrospective · " : ""}Estimated 10th–90th percentile range</p>
      <table><thead><tr><th>Stat</th><th>Estimate</th><th>Low</th><th>High</th></tr></thead>
        <tbody>{Object.entries(projection.stats).map(([stat, value]) =>
          <tr key={stat}><th scope="row">{stat.toUpperCase()}</th><td>{value.mean}</td><td>{value.low}</td><td>{value.high}</td></tr>)}</tbody>
      </table>
    </div>}
  </>;
}
export default function Page() { return <Suspense fallback={<p>Loading players…</p>}><Players /></Suspense>; }
