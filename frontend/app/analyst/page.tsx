"use client";

import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { api, Chat, errorMessage, Game, percent } from "../../lib/api";
import { gameDrivers, gameLabel, modelAnswer, readableDate } from "../../lib/presentation";
import { Notice, PageTitle } from "../components";

const sources: Record<string, string> = {
  get_todays_games: "Scoreboard", get_win_probability: "Pregame forecast", get_live_probability: "Play-by-play",
  get_player_projection: "Player projection model", get_prediction_drivers: "Model factors", get_team_recent_form: "Recent team results",
};

const matchupQuestions = ["Who was favored before tipoff?", "What factors shaped the forecast?", "How did the win chances change?"];

async function matchupAnswer(game: Game, question: string): Promise<Chat | undefined> {
  if (question === matchupQuestions[2]) {
    const live = await api.live(game.game_id);
    const first = live.points.at(0);
    const last = live.points.at(-1);
    if (!first || !last) return { answer: "No play-by-play estimates are available yet.", evidence: [] };
    const peak = Math.max(...live.points.map(point => point.home_win_prob));
    return { answer: `The ${game.home} opened at ${percent(first.home_win_prob)} in the first plotted state. Their win chance peaked at ${percent(peak)} and finished the plotted sequence at ${percent(last.home_win_prob)}.`,
      evidence: [{ tool: "get_live_probability" }] };
  }
  if (!matchupQuestions.slice(0, 2).includes(question)) return;
  const result = await api.prediction(game.game_id);
  if (question === matchupQuestions[0]) {
    const p = result.home_win_prob;
    const answer = p === .5 ? "The pregame model gave both teams a 50% chance."
      : `Before tipoff, the model favored the ${p > .5 ? game.home : game.away} with a ${percent(Math.max(p, 1-p))} chance of winning.`;
    return { answer, evidence: [{ tool: "get_win_probability" }] };
  }
  const factors = gameDrivers(result.drivers);
  return { answer: factors.length ? factors.map(factor => `${factor.title} favored the ${game[factor.favors]}. ${factor.explanation}`).join("\n")
    : "The model returned a forecast without a factor breakdown.",
    evidence: [{ tool: "get_prediction_drivers" }] };
}

function Analyst() {
  const key = useSearchParams().get("matchup");
  const [game, setGame] = useState<Game>();
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<{ question: string; result: Chat }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const suggestions = game ? matchupQuestions : [
    "Are there any games today?", "How have the Celtics played recently?", "Which completed games can I replay?",
  ];

  useEffect(() => {
    let active = true;
    if (key) api.matchup(key).then(g => { if (active) setGame(g); }).catch(() => {});
    return () => { active = false; };
  }, [key]);

  async function ask(event: FormEvent) {
    event.preventDefault();
    const prompt = question.trim();
    if (!prompt || busy) return;
    setBusy(true); setError("");
    try {
      const direct = game ? await matchupAnswer(game, prompt) : undefined;
      const result = direct ?? await api.chat(game
        ? `For ${gameLabel(game)} on ${game.game_date} (internal reference ${game.game_id}), ${prompt}`
        : prompt);
      setHistory(items => [...items, { question: prompt, result }]); setQuestion("");
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }

  return <>
    <PageTitle label="AI analyst" title="Ask about the game." description="Get an explanation based on the scoreboard, prediction models, and recent team results." />
    <section className="panel analyst-panel">
      {game && <p className="analyst-context"><strong>{gameLabel(game)}</strong> · {readableDate(game.game_date)}</p>}
      <form className="ask-form" onSubmit={ask}>
        <label>Your question<input value={question} onChange={event => setQuestion(event.target.value)} required maxLength={game ? 360 : 500} placeholder="Ask about a matchup, team, or player" /></label>
        <button className="button primary" disabled={busy}>{busy ? "Checking data…" : "Ask Courtside"} <span aria-hidden="true">↗</span></button>
      </form>
      <div className="suggestions" aria-label="Suggested questions">{suggestions.map(item => <button key={item} onClick={() => setQuestion(item)}>{item} <span aria-hidden="true">↗</span></button>)}</div>
      {error && <p className="notice" role="alert">{error}</p>}
      <div className="chat-history" aria-live="polite">{history.map(({ question, result }, index) => <article key={index}>
        <h2>{question}</h2><p className="answer">{modelAnswer(result.answer)}</p>
        {!!result.evidence.length && <p className="sources">Sources used · {[...new Set(result.evidence.map(item => sources[item.tool]).filter(Boolean))].join(" · ")}</p>}
      </article>)}</div>
    </section>
  </>;
}
export default function Page() {
  return <Suspense fallback={<Notice>Loading analyst…</Notice>}><Analyst /></Suspense>;
}
