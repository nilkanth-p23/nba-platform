"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "../../../lib/api";
import { gameHref } from "../../../lib/presentation";
import { Notice } from "../../components";

export default function LegacyGameLink() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    api.prediction(id).then(game => { if (active) router.replace(gameHref(game)); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [id, router]);
  return <><Link className="back-link" href="/#scoreboard">← Scoreboard</Link><Notice>{failed ? "This matchup is unavailable." : "Opening matchup…"}</Notice></>;
}
