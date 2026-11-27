"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  ["/", "Games"], ["/players", "Players"], ["/analyst", "AI analyst"], ["/performance", "Model results"],
];

export function NavLinks() {
  const pathname = usePathname();
  return <div className="nav-links">{links.map(([href, label]) => {
    const active = href === "/" ? pathname === "/" || pathname.startsWith("/matchups/") : pathname.startsWith(href);
    return <Link key={href} href={href} aria-current={active ? "page" : undefined}>{label}</Link>;
  })}</div>;
}
