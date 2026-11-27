"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage, percent } from "../../lib/api";
import { Notice, PageTitle } from "../components";

export default function Performance() {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.performance>>>();
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.performance().then(value => { if (active) setData(value); })
      .catch(err => { if (active) setError(errorMessage(err)); });
    return () => { active = false; };
  }, []);
  return <>
    <PageTitle label="Model evaluation" title="How well does it predict?" description="See how the models performed on games held back from training, and follow forecasts as new results come in." />
    <section aria-labelledby="historical-results" className="evaluation">
      <div className="section-head"><div><h2 id="historical-results">Historical test results</h2><p>2025–26 NBA regular season.</p></div></div>
      <div className="grid">
        <article className="panel metric-card"><p className="kicker">Pregame winner</p><strong>67.5%</strong><p>of game winners correctly picked before tipoff.</p></article>
        <article className="panel metric-card"><p className="kicker">In-game winner</p><strong>77.9%</strong><p>accuracy across sampled moments during games.</p></article>
        <article className="panel metric-card"><p className="kicker">Player scoring</p><strong>4.83 pts</strong><p>average points projection error, versus 4.96 for a 10-game average.</p></article>
      </div>
      <details className="panel methodology">
        <summary>How to read the scores</summary>
        <p><strong>Accuracy</strong> is how often the favored team won. <strong>Brier score</strong> measures the gap between win probabilities and actual outcomes. A lower score means better probabilities.</p>
        <p><strong>Calibration</strong> checks whether games given similar odds finish at the expected rate. For example, teams given a 60% chance should win about six out of ten times.</p>
        <p>These results come from held-out 2025–26 evaluations. The deployed models were subsequently refit using more data. Historical replays illustrate changing win chances rather than prospective performance.</p>
      </details>
    </section>
    <section aria-labelledby="new-results">
      <div className="section-head"><div><h2 id="new-results">Published forecasts</h2><p>Forecasts saved before tipoff and scored after the final buzzer.</p></div></div>
      {error && <Notice>{error}</Notice>}
      {!data && !error && <Notice>Loading published forecast results…</Notice>}
      {data && !data.models.length && <Notice>Charts appear once a saved pregame forecast has a final score. Historical test results are shown above.</Notice>}
      {data?.models.map(model => <section className="panel" key={model.version}>
        <h3>Pregame model</h3>
        <div className="table-wrap"><table><thead><tr><th>Method</th><th>Games</th><th>Accuracy</th><th>Brier score</th></tr></thead>
          <tbody>{([["Prediction model", model.summary], ["Team rating only", model.elo], ["Always pick home", model.always_home]] as const).map(([name, m]) =>
            m && <tr key={name}><th scope="row">{name}</th><td>{m.count}</td><td>{percent(m.accuracy)}</td><td>{m.brier.toFixed(3)}</td></tr>)}</tbody>
        </table></div>
        <h3>Accuracy over time</h3><p className="muted">Each point uses up to the previous {data.window_games} games.</p>
        <div className="chart"><ResponsiveContainer><LineChart data={model.rolling}>
          <CartesianGrid stroke="#e8e1d8" /><XAxis dataKey="date" /><YAxis domain={[0, 1]} tickFormatter={percent} /><Tooltip formatter={value => percent(Number(value))} />
          <Line dataKey="accuracy" stroke="#c64a2b" dot={false} />
        </LineChart></ResponsiveContainer></div>
        <h3>Predicted versus actual</h3>
        <div className="chart"><ResponsiveContainer><LineChart data={model.calibration}>
          <CartesianGrid stroke="#e8e1d8" /><XAxis dataKey="predicted" type="number" domain={[0, 1]} tickFormatter={percent} />
          <YAxis domain={[0, 1]} tickFormatter={percent} /><Tooltip formatter={value => percent(Number(value))} />
          <Line dataKey="actual" name="Actual home win rate" stroke="#c64a2b" />
          <Line dataKey="predicted" name="Perfect calibration" stroke="#547371" strokeDasharray="4 4" />
        </LineChart></ResponsiveContainer></div>
      </section>)}
    </section>
  </>;
}
