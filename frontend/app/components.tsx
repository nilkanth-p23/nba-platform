import type { CSSProperties, ReactNode } from "react";
import { teamNames } from "../lib/presentation";

const colors: Record<string, string> = {
  ATL:"#ad1f3e", BOS:"#13744c", CLE:"#7f2038", NOP:"#8b6d3e", CHI:"#b42139",
  DAL:"#185ca7", DEN:"#87600e", GSW:"#3158a0", HOU:"#ae1b33", LAC:"#ad213c",
  LAL:"#633d8a", MIA:"#941b3d", MIL:"#31563e", MIN:"#395273", BKN:"#303032",
  NYK:"#2456a3", ORL:"#235b96", IND:"#806019", PHI:"#1f5caa", PHX:"#6a3e8f",
  POR:"#a82e3d", SAC:"#64448b", SAS:"#4a5055", OKC:"#137599", TOR:"#9f2340",
  UTA:"#554695", MEM:"#435b8a", WAS:"#9b263b", DET:"#2455a1", CHA:"#247677",
};

export function TeamBadge({ id, name }: { id: number; name: string }) {
  const short = teamNames[id] || name.slice(0, 3).toUpperCase();
  return <span aria-hidden="true" className="team-badge" style={{ "--team": colors[short] || "#4b555a" } as CSSProperties}>{short}</span>;
}

export function PageTitle({ title, description, label }: { title: string; description: string; label: string }) {
  return <section className="page-title"><p className="kicker">{label}</p><h1>{title}</h1><p>{description}</p></section>;
}

export function Notice({ children }: { children: ReactNode }) {
  return <p className="notice" role="status">{children}</p>;
}
