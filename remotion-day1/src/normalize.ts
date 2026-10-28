import type { Action, ReviewShow } from "./types";
const numberOrPending = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
// Rendering tolerates incomplete optional fields. Official snapshot validation
// still rejects unverified totals/picks upstream; this never invents zeroes.
export const normalizeForRender = (show: ReviewShow): ReviewShow => ({
  ...show,
  players: show.players.map((p) => ({
    ...p,
    name: p.name || "Data pending",
    team: p.team || "—",
    position: p.position || p.pos || "—",
    points: numberOrPending(p.points),
    minutes: numberOrPending(p.minutes),
    price: numberOrPending(p.price),
    ownership: numberOrPending(p.ownership),
    goals: numberOrPending(p.goals),
    assists: numberOrPending(p.assists),
    clean_sheets: numberOrPending(p.clean_sheets),
    saves: numberOrPending(p.saves),
    bonus: numberOrPending(p.bonus),
    photo: p.photo || "",
    badge: p.badge || "",
    fixtures: (Array.isArray(p.fixtures) && p.fixtures.length
      ? p.fixtures
      : p.next_fixture
        ? [p.next_fixture]
        : []
    ).filter((f) => f && f.opp && f.gw && f.ha),
    isCaptain: !!(p.isCaptain || p.captain),
    isViceCaptain: !!(p.isViceCaptain || p.vice),
    isBench: !!(p.isBench || p.bench),
    availability: p.availability || p.status || "u",
    status_reason: p.status_reason || p.news || "",
    verdict: p.verdict || "MONITOR",
    analysis: p.analysis || "Data pending",
    event_summary: p.event_summary || "Data pending",
    action: ([
      "goal",
      "assist",
      "clean-sheet",
      "saves",
      "captain",
      "bench-haul",
      "injury",
      "blank",
      "points",
    ].includes(p.action)
      ? p.action
      : "points") as Action,
  })),
});
export const pointsText = (value: number | null | undefined) =>
  value == null ? "Data pending" : String(value);
