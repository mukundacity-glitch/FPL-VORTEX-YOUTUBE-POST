import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { ReviewPlayer } from "../types";
import { cardTokens, clubColors } from "../brand";
import { EventIcon, type IconName } from "./EventIcon";
import { SafeImage, Shirt } from "./Media";
import { VerdictBadge } from "./VerdictBadge";
export type CardVariant =
  | "Top Performer"
  | "Warning"
  | "Captain"
  | "Bench Haul"
  | "Injury Doubt"
  | "Clean Sheet"
  | "Standard Review";
const pending = (value?: number | null) =>
  value === null || value === undefined ? "Data pending" : String(value);
const pair = (a?: number | null, b?: number | null) =>
  a == null || b == null ? "Data pending" : `${a} / ${b}`;
export const PlayerCard: React.FC<{
  player: ReviewPlayer;
  variant?: CardVariant;
  verdict?: string;
}> = ({ player: p, variant = "Standard Review", verdict }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const accent = /Warning|Injury/.test(variant)
    ? cardTokens.amber
    : variant === "Bench Haul"
      ? cardTokens.red
      : variant === "Top Performer"
        ? cardTokens.green
        : cardTokens.cyan;
  const stats: { kind: IconName; label: string; value: string }[] = [
    { kind: "clock", label: "MINUTES", value: pending(p.minutes) },
    { kind: "goal", label: "GOALS / ASSISTS", value: pair(p.goals, p.assists) },
    {
      kind: p.position === "GK" ? "saves" : "clean-sheet",
      label:
        p.position === "GK" ? "SAVES / CLEAN SHEETS" : "CLEAN SHEETS / BONUS",
      value:
        p.position === "GK"
          ? pair(p.saves, p.clean_sheets)
          : pair(p.clean_sheets, p.bonus),
    },
  ];
  const parts = p.name.split(" ");
  const last = parts.length > 1 ? parts.slice(1).join(" ") : p.name;
  return (
    <article
      className="vx-player-card"
      data-player-id={p.id}
      data-variant={variant}
      style={
        {
          "--card-accent": accent,
          "--club": clubColors[p.team] || "#6635bc",
          "--card-radius": `${cardTokens.radius}px`,
          rotate: `${interpolate(frame, [0, 0.8 * fps], [-1.8, 0], { extrapolateRight: "clamp" })}deg`,
        } as React.CSSProperties
      }
    >
      <div className="vx-card-top">
        <span>
          FPL <em>VORTEX</em>
        </span>
        <b>{p.position}</b>
      </div>
      <div className="vx-card-hero">
        <div className="vx-card-watermark">V</div>
        <div className="vx-role">
          {p.isCaptain
            ? "CAPTAIN"
            : p.isViceCaptain
              ? "VICE CAPTAIN"
              : variant === "Top Performer"
                ? "FORM ALERT"
                : variant === "Bench Haul"
                  ? "BENCH REGRET"
                  : variant === "Injury Doubt"
                    ? "AVAILABILITY WATCH"
                    : variant.toUpperCase()}
        </div>
        <div className="vx-card-points">
          {p.points == null
            ? "—"
            : Math.round(
                p.points *
                  interpolate(frame, [0.3 * fps, 1.2 * fps], [0, 1], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  }),
              )}
          <small>GW POINTS</small>
        </div>
        <div
          className="vx-card-portrait"
          style={{
            translate: `0px ${(1 - spring({ frame: frame - 3, fps, config: { damping: 24 } })) * 35}px`,
          }}
        >
          <SafeImage
            src={p.photo}
            fallback={<Shirt color={clubColors[p.team]} label={p.team} />}
          />
        </div>
        <div className="vx-card-identity">
          <div className="vx-crest">
            <SafeImage
              src={p.badge}
              fallback={<span>{p.team.slice(0, 3)}</span>}
            />
          </div>
          <div>
            <small>{parts.length > 1 ? parts[0] : "PLAYER FILE"}</small>
            <strong
              style={{
                fontSize: last.length > 21 ? 37 : last.length > 14 ? 43 : 54,
              }}
            >
              {last}
            </strong>
            <b>{p.team_name || p.team}</b>
          </div>
        </div>
      </div>
      <div className="vx-card-ribbon">
        <div>
          <small>PRICE</small>
          <strong style={{ fontSize: p.price == null ? 23 : 34 }}>
            {p.price == null ? "Data pending" : `£${p.price.toFixed(1)}M`}
          </strong>
        </div>
        <div>
          <small>OWNERSHIP</small>
          <strong style={{ fontSize: p.ownership == null ? 23 : 34 }}>
            {p.ownership == null
              ? "Data pending"
              : `${p.ownership.toFixed(1)}%`}
          </strong>
        </div>
      </div>
      <div className="vx-card-stats">
        {stats.map((s, i) => (
          <div
            key={s.label}
            style={{
              opacity: interpolate(
                frame,
                [fps * (0.55 + i * 0.15), fps * (0.8 + i * 0.15)],
                [0, 1],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
              ),
            }}
          >
            <span className="vx-stat-icon">
              <EventIcon kind={s.kind} />
            </span>
            <b>{s.label}</b>
            <strong style={{ fontSize: s.value === "Data pending" ? 17 : 26 }}>
              {s.value}
            </strong>
          </div>
        ))}
      </div>
      <div className="vx-card-fixtures">
        <div className="vx-fixture-title">
          <EventIcon kind="fixture" size={22} /> NEXT{" "}
          {Math.min(5, p.fixtures?.length || 1)} FIXTURE
          {(p.fixtures?.length || 0) > 1 ? "S" : ""}
        </div>
        <div className="vx-fixture-grid">
          {p.fixtures?.length ? (
            p.fixtures.slice(0, 5).map((f, i) => (
              <div key={`${f.gw}-${i}`}>
                <small>GW{f.gw}</small>
                <b>{f.opp}</b>
                <span>({f.ha})</span>
                {f.difficulty ? (
                  <i
                    style={{
                      background:
                        f.difficulty <= 2
                          ? "#21e97e"
                          : f.difficulty >= 4
                            ? "#ff4863"
                            : "#ffcd19",
                    }}
                  >
                    {f.difficulty}
                  </i>
                ) : null}
              </div>
            ))
          ) : (
            <span>Data pending</span>
          )}
        </div>
      </div>
      <div className="vx-card-bottom">
        <VerdictBadge verdict={verdict || p.verdict} delay={fps * 1.1} />
        <p>
          {p.availability !== "a" && p.status_reason
            ? p.status_reason
            : p.analysis}
        </p>
      </div>
    </article>
  );
};
