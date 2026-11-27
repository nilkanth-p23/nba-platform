"use client";

import { FormEvent, useState } from "react";
import { api, Chat, errorMessage } from "../../lib/api";

const suggestions = ["How have the Celtics done in their last five games?", "What games are scheduled today?"];

export default function Analyst() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<{ question: string; result: Chat }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const result = await api.chat(question.trim());
      setHistory(items => [...items, { question, result }]); setQuestion("");
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <><h1>AI analyst</h1><p className="muted">Ask about a team, game, or player. Include the matchup and game ID when you have it.</p>
    <div className="players">{suggestions.map(item => <button key={item} onClick={() => setQuestion(item)}>{item}</button>)}</div>
    <form className="panel form" onSubmit={ask}>
      <label className="grow">Question<input value={question} onChange={e => setQuestion(e.target.value)}
        maxLength={500} required placeholder="Ask about an NBA matchup" /></label>
      <button disabled={busy}>{busy ? "Analyzing…" : "Send"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    <div aria-live="polite">{history.map(({ question, result }, i) => <article className="panel" key={i}>
      <h2>{question}</h2><p className="answer">{result.answer}</p>
      {!!result.evidence.length && <details><summary>Model and database results</summary><pre>{JSON.stringify(result.evidence, null, 2)}</pre></details>}
    </article>)}</div>
  </>;
}
