import type { Metadata } from "next";
import Link from "next/link";
import "@fontsource-variable/dm-sans";
import "@fontsource/barlow-condensed/700.css";
import "@fontsource/barlow-condensed/800.css";
import { NavLinks } from "./navigation";
import "./style.css";

export const metadata: Metadata = {
  title: "Courtside | NBA Prediction Model Analysis",
  description: "Explore NBA win probabilities, game replays, player projections, and the data behind each forecast.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>
    <a className="skip-link" href="#content">Skip to content</a>
    <header className="site-header"><nav aria-label="Main navigation" className="shell">
      <Link className="wordmark" href="/"><span className="brand-icon" aria-hidden="true"><i /></span>Courtside<span className="brand-dot">.</span></Link>
      <NavLinks />
    </nav></header>
    <main id="content" className="shell">{children}</main>
    <footer className="shell site-footer"><span>Courtside · NBA prediction model analysis</span><span>Independent educational project. No betting advice.</span></footer>
  </body></html>;
}
