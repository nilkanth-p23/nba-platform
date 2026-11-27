"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage, percent } from "../../lib/api";

export default function Performance() {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.performance>>>();
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.performance().then(value => { if (active) setData(value); })
      .catch(err => { if (active) setError(errorMessage(err)); });
    return () => { active = false; };
  }, []);
  return <><h1>Model performance</h1>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p role="status">Loading performance…</p>}
    {data && !data.models.length && <p className="panel">Results appear after a scheduled game receives a saved forecast and its final score is recorded.</p>}
    {data?.models.map(model => <section className="panel" key={model.version}>
      <h2>{model.version}</h2>
      <table><thead><tr><th>Method</th><th>Games</th><th>Accuracy</th><th>Brier</th><th>Log loss</th></tr></thead>
        <tbody>{([["Model", model.summary], ["Elo", model.elo], ["Always home", model.always_home]] as const).map(([name, m]) =>
          m && <tr key={name}><th scope="row">{name}</th><td>{m.count}</td><td>{percent(m.accuracy)}</td><td>{m.brier.toFixed(3)}</td><td>{m.log_loss.toFixed(3)}</td></tr>)}</tbody>
      </table>
      <h3>Last {data.window_games} games per point</h3>
      <div className="chart"><ResponsiveContainer><LineChart data={model.rolling}>
        <CartesianGrid stroke="#253b38" /><XAxis dataKey="date" /><YAxis domain={[0, 1]} /><Tooltip />
        <Line dataKey="accuracy" stroke="#a6f180" dot={false} /><Line dataKey="brier" stroke="#ffbb7a" dot={false} />
      </LineChart></ResponsiveContainer></div>
      <h3>Calibration</h3>
      <div className="chart"><ResponsiveContainer><LineChart data={model.calibration}>
        <CartesianGrid stroke="#253b38" /><XAxis dataKey="predicted" type="number" domain={[0, 1]} tickFormatter={percent} />
        <YAxis domain={[0, 1]} tickFormatter={percent} /><Tooltip />
        <Line dataKey="actual" name="Observed home win rate" stroke="#a6f180" />
        <Line dataKey="predicted" name="Perfect calibration" stroke="#879e98" strokeDasharray="4 4" />
      </LineChart></ResponsiveContainer></div>
    </section>)}
  </>;
}
