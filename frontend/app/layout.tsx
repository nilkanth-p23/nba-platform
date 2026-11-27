import type { Metadata } from "next";
import Link from "next/link";
import "./style.css";

export const metadata: Metadata = { title: "Courtside | NBA Predictions", description: "NBA win probabilities and player projections." };

export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>
    <header><nav aria-label="Main">
      <Link className="brand" href="/">COURTSIDE<span>.</span></Link>
      <div><Link href="/">Games</Link><Link href="/players">Players</Link>
        <Link href="/performance">Performance</Link><Link href="/analyst">Analyst</Link></div>
    </nav></header>
    <main>{children}</main>
    <footer>Educational model estimates. No betting advice.</footer>
  </body></html>;
}
