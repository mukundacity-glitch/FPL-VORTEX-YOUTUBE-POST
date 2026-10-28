import type { Beat, Player, Show } from "./types";

// Keep the original renderer's evidence, labels and fixture rotation.
export const evidenceFor = (
  show: Show,
  beat: Beat,
  player: Player,
): [string, string, string] => {
  if (beat.section === "hook")
    return ["C", "Captain points", String(show.accuracy.captain_points)];
  if (beat.section === "story")
    return ["✓", "Points counted", String(player.points)];
  if (beat.section === "decision_1" && beat.variant === 0)
    return ["↗", "Season starts", String(player.season_starts ?? "—")];
  if (beat.section === "decision_2" && beat.variant === 1)
    return [
      "↗",
      player.bench ? "Unused bench" : "GW points",
      String(player.points),
    ];
  if (beat.section === "decision_3")
    return [
      "!",
      "Official update",
      player.status === "a" ? "Available" : "Team news needed",
    ];
  const fixture = player.next_fixture;
  return [
    "↗",
    "Next fixture",
    fixture?.opp ? `${fixture.opp} · ${fixture.ha}` : "Not confirmed",
  ];
};

export const sectionLabels: Record<string, string> = {
  hook: "The captain call",
  story: "What actually counted",
  decision_1: "Decision 01",
  decision_2: "Decision 02",
  decision_3: "Decision 03",
  plan: "My early plan",
  cta: "Your decision",
};
