import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { ReviewPlayer, ReviewSection, ReviewShow } from "../types";
import { PlayerCard, type CardVariant } from "../components/PlayerCard";
import { pitchPositions } from "../components/AnimatedSquadPitch";
import { VerdictBadge } from "../components/VerdictBadge";
import { ScoreTile } from "../components/ScoreTile";
import { EventIcon } from "../components/EventIcon";
import { SafeImage, Shirt } from "../components/Media";
import { clubColors } from "../brand";
import { pointsText } from "../normalize";
export type SceneProps = { show: ReviewShow; section: ReviewSection };
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const getPlayer = ({ show, section }: SceneProps) =>
  show.players.find((p) => p.id === section.player_id)!;
const MiniPlayer: React.FC<{
  player: ReviewPlayer;
  label: string;
  color: string;
}> = ({ player: p, label, color }) => (
  <div
    className="vx-mini-player"
    style={{ "--mini-color": color } as React.CSSProperties}
  >
    <div>
      <SafeImage
        src={p.photo}
        fallback={<Shirt color={clubColors[p.team]} label={p.team} />}
      />
    </div>
    <small>{label}</small>
    <b>{p.name}</b>
    <strong style={{ fontSize: p.points == null ? 28 : 69 }}>
      {pointsText(p.points)}
      <span> PTS</span>
    </strong>
    <EventIcon kind={p.action} size={32} />
  </div>
);
export const OpeningSequence: React.FC<SceneProps> = ({ show }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const captain = show.players.find(
    (p) => p.id === show.accuracy.effective_captain_id,
  )!;
  const best = show.players
    .filter((p) => (p.multiplier || 0) > 0)
    .sort((a, b) => (b.points ?? -Infinity) - (a.points ?? -Infinity))[0];
  const regret = show.players.find(
    (p) => p.id === show.accuracy.actual_bench_regret_id,
  );
  return (
    <>
      <div className="vx-opening-score">
        <div className="vx-eyebrow">THE GAMEWEEK TURNING POINT</div>
        <h1>
          {regret
            ? "Points won."
            : show.accuracy.captain_points <= 4
              ? "The armband."
              : "Points on the board."}
          <br />
          <em>
            {regret
              ? "Points left behind."
              : show.accuracy.captain_points <= 4
                ? "A decision to revisit."
                : "The next decision."}
          </em>
        </h1>
        <strong>
          {Math.round(
            show.accuracy.gw_points *
              interpolate(frame, [0, fps * 1.4], [0, 1], clamp),
          )}
          <span> GAMEWEEK POINTS</span>
        </strong>
        <div className="vx-captain-equation">
          <EventIcon kind="captain" /> {pointsText(captain.points)} ×{" "}
          {captain.multiplier ?? "Data pending"} ={" "}
          <b>{show.accuracy.captain_points}</b>
          <small> ACTUAL CAPTAIN CONTRIBUTION</small>
        </div>
      </div>
      <div className="vx-opening-orbit">
        {[
          {
            p: captain,
            label: "THE ARMBAND",
            color: show.accuracy.captain_points <= 4 ? "#ff4863" : "#59dcff",
          },
          {
            p: regret || best,
            label: regret ? "BENCH REGRET" : "BEST RETURN",
            color: regret ? "#ff4863" : "#43fb8b",
          },
          { p: best, label: "POINTS THAT COUNTED", color: "#43fb8b" },
        ].map(({ p, label, color }, i) => (
          <div
            key={label}
            style={{
              translate: `${(1 - spring({ frame: frame - i * 0.25 * fps, fps, config: { damping: 22 } })) * 220}px ${Math.sin((frame / fps) * 0.7 + i) * 6}px`,
              rotate: `${[-3, 3, -1][i]}deg`,
            }}
          >
            <MiniPlayer player={p} label={label} color={color} />
          </div>
        ))}
      </div>
    </>
  );
};
export const MatchweekHighlights: React.FC<SceneProps> = ({ show }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const index = Math.floor(frame / (fps * 5));
  return (
    <>
      <div className="vx-pitch-tag">
        <span className="vx-live-dot" /> THE GAMEWEEK IN FOCUS
      </div>
      <aside className="vx-match-carousel">
        <div className="vx-eyebrow">FPL-RELEVANT RESULTS</div>
        {show.matches.length ? (
          [0, 1, 2].map((offset) => {
            const m = show.matches[(index + offset) % show.matches.length];
            return (
              <ScoreTile
                key={`${index}-${offset}`}
                match={m}
                active={offset === 0}
              />
            );
          })
        ) : (
          <>
            <div className="vx-pending-tile">
              MATCH RESULTS
              <br />
              <b>Data pending</b>
            </div>
            {show.top_ids.slice(0, 2).map((id) => (
              <MiniPlayer
                key={id}
                player={show.players.find((p) => p.id === id)!}
                label="VERIFIED SQUAD RETURN"
                color="#43fb8b"
              />
            ))}
          </>
        )}
        <p className="vx-scope">{show.performer_scope}</p>
      </aside>
    </>
  );
};
const HeroFromPitch: React.FC<SceneProps & { variant: CardVariant }> = ({
  show,
  section,
  variant,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = getPlayer({ show, section });
  const starters = show.players.filter(
    (p) => show.package.players.some((o) => o.id === p.id) && !p.isBench,
  );
  const bench = show.players.filter(
    (p) => show.package.players.some((o) => o.id === p.id) && p.isBench,
  );
  const point = pitchPositions(starters, bench)[p.id] || {
    x: 580,
    y: p.position === "FWD" ? 520 : p.position === "MID" ? 370 : 225,
  };
  const enter = spring({
    frame,
    fps,
    config: { damping: 23, stiffness: 105 },
    durationInFrames: fps * 0.9,
  });
  const depart = interpolate(
    frame,
    [Math.max(1, (section.duration - 0.3) * fps), section.duration * fps],
    [1, 0.94],
    clamp,
  );
  return (
    <div
      className={`vx-hero-motion action-${section.action}`}
      style={{
        translate: `${(point.x + 64 - 1300 - (548 * 0.17) / 2) * (1 - enter)}px ${(point.y + 150 - 145 - (780 * 0.17) / 2) * (1 - enter)}px`,
        scale: (0.17 + 0.83 * enter) * depart,
        opacity: interpolate(frame, [0, 0.15 * fps], [0, 1], clamp),
        rotate: `${(1 - enter) * (section.action === "goal" ? -8 : section.action === "assist" ? 7 : 2)}deg`,
        transformOrigin: "0 0",
      }}
    >
      <PlayerCard player={p} variant={variant} verdict={section.verdict} />
    </div>
  );
};
export const TopPerformers: React.FC<SceneProps> = (props) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = getPlayer(props);
  if (props.section.id === "top_radar")
    return (
      <aside className="vx-match-carousel">
        <div className="vx-eyebrow vx-positive">THREE FORM ALERTS</div>
        {props.show.top_ids.map((id) => (
          <MiniPlayer
            key={id}
            player={props.show.players.find((p) => p.id === id)!}
            label="THE FORM RADAR"
            color="#43fb8b"
          />
        ))}
      </aside>
    );
  return (
    <>
      <div className="vx-zone-analysis">
        <div className="vx-eyebrow vx-positive">
          FORM ALERT · {props.show.top_ids.indexOf(p.id) + 1} / 3
        </div>
        <h2>{p.name}</h2>
        <div className="vx-return-counter">
          {p.points == null
            ? "Data pending"
            : Math.round(
                p.points * interpolate(frame, [0, fps], [0, 1], clamp),
              )}
          <small> POINTS</small>
        </div>
        <div className="vx-event-chips">
          {(["goals", "assists", "clean_sheets", "bonus"] as const).map(
            (key, i) =>
              p[key] != null ? (
                <span
                  key={key}
                  style={{
                    opacity: interpolate(
                      frame,
                      [fps * (0.6 + i * 0.2), fps * (0.9 + i * 0.2)],
                      [0, 1],
                      clamp,
                    ),
                  }}
                >
                  <EventIcon
                    kind={
                      key === "goals"
                        ? "goal"
                        : key === "assists"
                          ? "assist"
                          : key === "clean_sheets"
                            ? "clean-sheet"
                            : "bonus"
                    }
                  />
                  {p[key]} {key.replace("_", " ")}
                </span>
              ) : null,
          )}
        </div>
        <p>{p.analysis}</p>
        <small className="vx-scope">{props.show.performer_scope}</small>
      </div>
      <HeroFromPitch {...props} variant="Top Performer" />
    </>
  );
};
export const WorstPerformers: React.FC<SceneProps> = (props) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = getPlayer(props);
  return (
    <>
      <div
        className="vx-zone-analysis vx-warning-zone"
        style={{
          borderColor: `rgba(255,72,99,${0.3 + Math.sin((frame / fps) * 2) * 0.1})`,
        }}
      >
        <div className="vx-eyebrow">
          DECISION CHECK · {props.show.worst_ids.indexOf(p.id) + 1} / 3
        </div>
        <h2>{p.name}</h2>
        <div className="vx-return-counter">
          {pointsText(p.points)}
          <small> POINTS</small>
        </div>
        <div className="vx-event-chips">
          <span>
            <EventIcon kind={p.action} />
            {p.minutes == null ? "Minutes pending" : `${p.minutes} MINUTES`}
          </span>
        </div>
        <p>
          {p.availability !== "a" && p.status_reason
            ? p.status_reason
            : p.analysis}
        </p>
        <VerdictBadge verdict={p.verdict} />
        <small className="vx-scope">{props.show.performer_scope}</small>
      </div>
      <HeroFromPitch
        {...props}
        variant={p.action === "injury" ? "Injury Doubt" : "Warning"}
      />
    </>
  );
};
export const MyGameweekSummary: React.FC<SceneProps> = ({ show }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const points = show.accuracy.gw_points,
    average = show.package.metrics.average_points;
  const max = Math.max(1, points, average || 0);
  const hero = show.players
    .filter((p) => (p.multiplier || 0) > 0)
    .sort((a, b) => (b.points ?? -Infinity) - (a.points ?? -Infinity))[0];
  const regret = show.players.find(
    (p) => p.id === show.accuracy.actual_bench_regret_id,
  );
  const active = Math.min(2, Math.floor(frame / (10 * fps)));
  return (
    <>
      <div className="vx-summary-chart">
        <div className="vx-eyebrow">MY GAMEWEEK STORY</div>
        <h2>
          {points} <span>vs</span> {average ?? "—"}
        </h2>
        {[
          { label: "MY SCORE", value: points, color: "#43fb8b" },
          { label: "GW AVERAGE", value: average, color: "#58dcff" },
        ].map((r, i) => (
          <div className="vx-score-bar" key={r.label}>
            <span>{r.label}</span>
            <div>
              <i
                style={{
                  width: `${((r.value == null ? 0 : r.value) / max) * 100 * interpolate(frame, [fps * 0.2 + i * 8, fps * 1.5 + i * 8], [0, 1], clamp)}%`,
                  background: r.color,
                }}
              />
            </div>
            <b>{r.value ?? "Data pending"}</b>
          </div>
        ))}
      </div>
      <aside className="vx-story-beats">
        {[
          {
            label: "BEST DECISION",
            name: hero.name,
            value: `${pointsText(hero.points)} PTS COUNTED`,
            color: "#43fb8b",
          },
          {
            label: regret ? "BIGGEST REGRET" : "LINEUP CHECK",
            name: regret?.name || "No unused bench upgrade",
            value: regret
              ? `${regret.points} PTS ON BENCH`
              : "Use minutes and role",
            color: "#ff4863",
          },
          {
            label: "CAPTAINCY OUTCOME",
            name: show.players.find(
              (p) => p.id === show.accuracy.effective_captain_id,
            )!.name,
            value: `${show.accuracy.captain_points} PTS COUNTED`,
            color: "#59dcff",
          },
        ].map((r, i) => (
          <div
            key={r.label}
            className={active === i ? "active" : ""}
            style={{ "--beat-color": r.color } as React.CSSProperties}
          >
            <small>{r.label}</small>
            <b>{r.name}</b>
            <strong>{r.value}</strong>
          </div>
        ))}
      </aside>
    </>
  );
};
export const FullSquadReveal: React.FC<SceneProps> = ({ show }) => (
  <aside className="vx-reveal-legend">
    <div className="vx-eyebrow">THE TEAM SHEET</div>
    <h2>{show.formation.join(" – ")}</h2>
    <p>Starting XI enter by formation line.</p>
    <div>
      <EventIcon kind="captain" /> Captain · actual selection
    </div>
    <div>
      <span className="vx-legend-vc">VC</span> Vice captain
    </div>
    <div>
      <EventIcon kind="injury" /> Verified availability flag
    </div>
    <div>
      <EventIcon kind="bench-haul" /> Unused bench return
    </div>
    <span className="vx-scope">
      Actual picks and multipliers.
      <br />
      No assumed substitutions.
    </span>
  </aside>
);
export const PlayerReviewSequence: React.FC<SceneProps> = (props) => {
  const p = getPlayer(props);
  const index = props.show.sections
    .filter((s) => s.scene === "reviews")
    .findIndex((s) => s.id === props.section.id);
  const variant: CardVariant =
    p.action === "captain"
      ? "Captain"
      : p.action === "injury"
        ? "Injury Doubt"
        : p.action === "clean-sheet"
          ? "Clean Sheet"
          : "Standard Review";
  return (
    <>
      <div className="vx-review-banner">
        <span>{String(index + 1).padStart(2, "0")} / 11 · STARTING XI</span>
        <b>{p.name}</b>
        <span>
          <EventIcon kind={p.action} />
          {p.event_summary}
        </span>
        {p.isCaptain ? (
          <strong>
            {pointsText(p.points)} × {p.multiplier ?? "Data pending"} ={" "}
            {p.points == null || p.multiplier == null
              ? "Data pending"
              : p.points * p.multiplier}{" "}
            COUNTED
          </strong>
        ) : null}
      </div>
      <HeroFromPitch {...props} variant={variant} />
    </>
  );
};
export const BenchReview: React.FC<SceneProps> = (props) => {
  const p = getPlayer(props);
  return (
    <>
      <div className="vx-review-banner">
        <span>BENCH & AVAILABILITY</span>
        <b>{p.name}</b>
        <span>
          <EventIcon kind={p.action} />
          {p.multiplier
            ? `${pointsText(p.points)} points · contribution counted`
            : p.action === "bench-haul"
              ? "BENCH REGRET"
              : p.availability !== "a" && p.status_reason
                ? "WAIT FOR TEAM NEWS"
                : "UNUSED BENCH"}
        </span>
      </div>
      <HeroFromPitch
        {...props}
        variant={
          p.action === "bench-haul"
            ? "Bench Haul"
            : p.action === "injury"
              ? "Injury Doubt"
              : "Standard Review"
        }
      />
    </>
  );
};
export const ClosingPlan: React.FC<SceneProps> = ({ show }) => (
  <aside className="vx-closing">
    <div className="vx-eyebrow">EARLY PLAN · GW{show.preview_gw}</div>
    {[show.decisions[1], show.decisions[0], show.decisions[2]].map((d, i) => (
      <div className="vx-next-step" key={d.player.id}>
        <small>
          {i === 0
            ? "EARLY STARTING CALL"
            : i === 1
              ? "CAPTAINCY TO MONITOR"
              : "WAIT FOR CONFIRMED NEWS"}
        </small>
        <b>{d.player.name}</b>
        <VerdictBadge verdict={d.verdict} />
      </div>
    ))}
    <div className="vx-question">
      <span>YOUR CALL</span>
      <p>{show.question}</p>
    </div>
  </aside>
);
export const SceneContent: React.FC<SceneProps> = (props) => {
  const components: Record<string, React.FC<SceneProps>> = {
    opening: OpeningSequence,
    highlights: MatchweekHighlights,
    top: TopPerformers,
    worst: WorstPerformers,
    summary: MyGameweekSummary,
    pitch: FullSquadReveal,
    reviews: PlayerReviewSequence,
    bench: BenchReview,
    closing: ClosingPlan,
  };
  const Component = components[props.section.scene];
  return Component ? <Component {...props} /> : null;
};
