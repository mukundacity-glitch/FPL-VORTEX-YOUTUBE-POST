import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { Match } from "../types";
import { clubColors } from "../brand";
import { EventIcon } from "./EventIcon";
export const ScoreTile: React.FC<{ match: Match; active?: boolean }> = ({
  match: m,
  active = true,
}) => {
  const timelineFrame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const frame = timelineFrame % (5 * fps);
  return (
    <div
      className={`vx-score-tile ${active ? "active" : ""}`}
      style={{
        borderLeftColor: clubColors[m.home] || "#69c9eb",
        borderRightColor: clubColors[m.away] || "#a15bf3",
        borderLeftWidth: 4,
        borderRightWidth: 4,
        opacity: interpolate(frame, [0, 0.25 * fps], [0, active ? 1 : 0.65], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }),
        translate: `0px ${interpolate(frame, [0, 0.5 * fps], [24, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}px`,
      }}
    >
      <small>FULL TIME · PREMIER LEAGUE</small>
      <div>
        <b>{m.home}</b>
        <strong>
          {m.home_score} <i>:</i> {m.away_score}
        </strong>
        <b>{m.away}</b>
      </div>
      <p>{m.story}</p>
      <div className="vx-match-events">
        {m.goals != null ? (
          <span>
            <EventIcon kind="goal" size={20} />
            {m.goals} GOALS
          </span>
        ) : null}
        {m.assists != null ? (
          <span>
            <EventIcon kind="assist" size={20} />
            {m.assists} ASSISTS
          </span>
        ) : null}
        {m.clean_sheets ? (
          <span>
            <EventIcon kind="clean-sheet" size={20} />
            {m.clean_sheets} CS
          </span>
        ) : null}
      </div>
    </div>
  );
};
