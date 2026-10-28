import React from "react";
import {
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { clubColors } from "../brand";
import type { Action, ReviewPlayer } from "../types";
import { EventIcon } from "./EventIcon";
import { SafeImage, Shirt } from "./Media";
export type PitchPoint = { x: number; y: number };
export const pitchPositions = (
  startingXI: ReviewPlayer[],
  bench: ReviewPlayer[],
): Record<number, PitchPoint> => {
  const points: Record<number, PitchPoint> = {};
  ["GK", "DEF", "MID", "FWD"].forEach((pos, row) => {
    const line = startingXI.filter((p) => p.position === pos);
    line.forEach((p, i) => {
      points[p.id] = {
        x: line.length === 1 ? 580 : 140 + (i * 880) / (line.length - 1),
        y: [80, 225, 370, 520][row],
      };
    });
  });
  bench.forEach((p, i) => {
    points[p.id] = { x: 180 + i * 267, y: 710 };
  });
  startingXI
    .filter((p) => !points[p.id])
    .forEach((p, i) => {
      points[p.id] = { x: 180 + i * 220, y: 595 };
    });
  return points;
};
const TacticalEvent: React.FC<{
  point: PitchPoint;
  action: Action;
  localFrame: number;
}> = ({ point, action, localFrame: f }) => {
  const { fps } = useVideoConfig();
  const progress = interpolate(f, [0.4 * fps, 1.7 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const fade = interpolate(f, [0, 0.3 * fps, 3 * fps, 4 * fps], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <svg
      className="vx-tactical-event"
      viewBox="0 0 1160 780"
      style={{ opacity: fade }}
    >
      {action === "goal" ? (
        <>
          <path
            d={`M${point.x} ${point.y} Q${point.x - 180} ${point.y / 2} 580 20`}
            stroke="#43fb8b"
            strokeWidth="6"
            fill="none"
            pathLength="1"
            strokeDasharray="1"
            strokeDashoffset={1 - progress}
          />
          <circle
            cx={
              (1 - progress) ** 2 * point.x +
              2 * (1 - progress) * progress * (point.x - 180) +
              progress ** 2 * 580
            }
            cy={
              (1 - progress) ** 2 * point.y +
              2 * (1 - progress) * progress * (point.y / 2) +
              progress ** 2 * 20
            }
            r="9"
            fill="white"
          />
          <rect
            x="535"
            y="4"
            width="90"
            height="32"
            rx="4"
            fill="none"
            stroke="#43fb8b"
            strokeWidth="3"
          />
        </>
      ) : null}
      {action === "assist" ? (
        <>
          <path
            d={`M${point.x} ${point.y} L580 510 L580 35`}
            fill="none"
            stroke="#58dcff"
            strokeWidth="5"
            strokeDasharray="12 8"
          />
          <circle
            cx={point.x + (580 - point.x) * progress}
            cy={point.y + (510 - point.y) * progress}
            r="7"
            fill="#58dcff"
          />
        </>
      ) : null}
      {action === "clean-sheet" ? (
        <path
          d={`M${point.x} ${point.y - 65} l65 28 v55 q0 50-65 78 q-65-28-65-78 v-55z`}
          fill="#43fb8b22"
          stroke="#43fb8b"
          strokeWidth="4"
          strokeDasharray="480"
          strokeDashoffset={(1 - progress) * 480}
        />
      ) : null}
      {["injury", "captain", "bench-haul", "saves", "points", "blank"].includes(
        action,
      ) ? (
        <circle
          cx={point.x}
          cy={point.y + 4}
          r={64 + progress * 34}
          fill="none"
          stroke={
            action === "injury"
              ? "#ffcd19"
              : action === "bench-haul"
                ? "#ff4863"
                : action === "blank"
                  ? "#8394a6"
                  : "#58dcff"
          }
          strokeWidth="3"
          strokeDasharray={action === "injury" ? "12 6" : "3 8"}
        />
      ) : null}
    </svg>
  );
};
const PlayerNode: React.FC<{
  player: ReviewPlayer;
  point: PitchPoint;
  index: number;
  selected: boolean;
  entranceFrame: number;
  captain?: number;
  viceCaptain?: number;
}> = ({
  player: p,
  point,
  index,
  selected,
  entranceFrame,
  captain,
  viceCaptain,
}) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const entrance = spring({
    frame: entranceFrame - index * 1.15 * fps,
    fps,
    config: { damping: 22, stiffness: 115 },
  });
  const color =
    p.action === "bench-haul"
      ? "#ff4863"
      : p.availability !== "a" && p.status_reason
        ? "#ffcd19"
        : selected
          ? "#43fb8b"
          : "#59dcff";
  const isCaptain = p.id === captain || p.isCaptain;
  return (
    <div
      className={`vx-player-node ${selected ? "selected" : ""} ${p.isBench ? "bench-node" : ""}`}
      data-node-id={p.id}
      data-selected={selected}
      style={
        {
          left: point.x - 86,
          top: point.y - (p.isBench ? 58 : 68),
          opacity: entrance,
          translate: `0px ${(1 - entrance) * (p.isBench ? 35 : 65)}px`,
          "--node-color": color,
          "--club": clubColors[p.team] || "#5199bf",
        } as React.CSSProperties
      }
    >
      <div className="vx-node-trail" style={{ height: (1 - entrance) * 100 }} />
      <div
        className="vx-node-halo"
        style={{
          opacity: selected ? 0.55 + Math.sin((f / fps) * 3) * 0.15 : 0.12,
        }}
      />
      <div className="vx-node-image">
        <SafeImage
          src={p.photo}
          fallback={<Shirt color={clubColors[p.team]} label={p.team} />}
        />
      </div>
      {isCaptain ? (
        <div
          className="vx-armband"
          style={{
            boxShadow: `0 0 ${8 + Math.sin((f / fps) * 4) * 4}px #46baff`,
          }}
        >
          C
        </div>
      ) : p.id === viceCaptain || p.isViceCaptain ? (
        <div className="vx-vc">VC</div>
      ) : null}
      {p.availability !== "a" && p.status_reason ? (
        <div className="vx-node-alert">
          <EventIcon kind="injury" size={24} />
        </div>
      ) : null}
      <div
        className="vx-node-name"
        style={{ fontSize: p.name.length > 16 ? 23 : 28 }}
      >
        {p.name}
      </div>
      <div className="vx-node-score">
        <span>{p.position}</span>
        <strong>
          {p.points == null ? "—" : p.points}
          <small> PTS</small>
        </strong>
        <EventIcon kind={p.action} size={20} />
      </div>
      {p.action === "bench-haul" ? (
        <div className="vx-bench-regret">BENCH REGRET</div>
      ) : (
        <div className="vx-node-detail">
          {p.price == null ? "Data pending" : `£${p.price.toFixed(1)}m`}
          {p.event_summary === "Data pending" ? "" : ` · ${p.event_summary}`}
        </div>
      )}
    </div>
  );
};
export type AnimatedSquadPitchProps = {
  formation: number[];
  startingXI: ReviewPlayer[];
  bench: ReviewPlayer[];
  captain?: number;
  viceCaptain?: number;
  selectedPlayer?: number;
  previousPlayer?: number;
  selectionFrame?: number;
  entranceStart?: number;
  points?: number | null;
  events?: Record<number, Action>;
  availability?: Record<number, string>;
};
export const AnimatedSquadPitch: React.FC<AnimatedSquadPitchProps> = ({
  formation,
  startingXI,
  bench,
  captain,
  viceCaptain,
  selectedPlayer,
  previousPlayer,
  selectionFrame = 0,
  entranceStart = -10,
  points,
  events,
  availability,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const positions = pitchPositions(startingXI, bench);
  const selected = positions[selectedPlayer || -1],
    previous = positions[previousPlayer || -1] || { x: 580, y: 300 };
  const camera = interpolate(selectionFrame, [0, fps * 0.9], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.2, 0.8, 0.2, 1),
  });
  const focus = selected
    ? {
        x: previous.x + (selected.x - previous.x) * camera,
        y: previous.y + (selected.y - previous.y) * camera,
      }
    : { x: 580, y: 300 };
  const player = [...startingXI, ...bench].find((p) => p.id === selectedPlayer);
  return (
    <div className="vx-pitch-wrap" data-component="AnimatedSquadPitch">
      <div className="vx-pitch-label">
        <span>
          MY SQUAD <b>{formation.join(" – ")}</b>
        </span>
        <span>
          {points == null ? "SCORE PENDING" : `${points} POINTS`} <i /> FINAL
          SNAPSHOT
        </span>
      </div>
      <div
        className="vx-pitch-camera"
        style={{
          scale: selected ? 1.035 : 1,
          translate: selected
            ? `${(580 - focus.x) * 0.035}px ${(300 - focus.y) * 0.035}px`
            : "0px 0px",
        }}
      >
        <svg
          className="vx-field"
          viewBox="0 0 1160 640"
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id="turf" x2="0" y2="1">
              <stop stopColor="#125f55" />
              <stop offset="1" stopColor="#087f53" />
            </linearGradient>
            <pattern
              id="stripes"
              width="1160"
              height="128"
              patternUnits="userSpaceOnUse"
            >
              <rect width="1160" height="64" fill="#ffffff06" />
            </pattern>
            <pattern
              id="net"
              width="14"
              height="14"
              patternUnits="userSpaceOnUse"
            >
              <path d="M14 0H0V14" fill="none" stroke="#b8ffed30" />
            </pattern>
          </defs>
          <path
            d="M76 10H1084L1150 630H10z"
            fill="url(#turf)"
            stroke="#5fe9c6"
            strokeWidth="2"
          />
          <path d="M76 10H1084L1150 630H10z" fill="url(#stripes)" />
          <g stroke="#c2ffeb80" strokeWidth="2.4" fill="none">
            <path d="M96 30h968l62 576H34zM64 320h1032" />
            <ellipse cx="580" cy="320" rx="114" ry="66" />
            <path d="M380 30v114h400V30M480 30v46h200V30M383 606V492h394v114M480 606v-46h200v46" />
            <path d="M475 144q105 63 210 0M475 492q105-63 210 0" />
          </g>
          <rect
            x="520"
            y="3"
            width="120"
            height="30"
            fill="url(#net)"
            stroke="#d0ffec"
          />
          <circle cx="580" cy="320" r="5" fill="#c2ffeb" />
          {[225, 370, 520].map((y) => (
            <path
              key={y}
              d={`M120 ${y}H1040`}
              fill="none"
              stroke="#5fffc4"
              strokeWidth="1"
              strokeDasharray="4 12"
              opacity={0.14 + 0.06 * Math.sin(frame / fps + y)}
            />
          ))}
        </svg>
        <div className="vx-bench-surface">
          <span>BENCH</span>
        </div>
        {[...startingXI, ...bench].map((p, i) => (
          <PlayerNode
            key={p.id}
            player={{
              ...p,
              action: events?.[p.id] || p.action,
              availability: availability?.[p.id] || p.availability,
            }}
            point={positions[p.id]}
            index={i}
            selected={p.id === selectedPlayer}
            entranceFrame={frame - entranceStart * fps}
            captain={captain}
            viceCaptain={viceCaptain}
          />
        ))}
        {selected && player ? (
          <TacticalEvent
            point={selected}
            action={events?.[player.id] || player.action}
            localFrame={selectionFrame}
          />
        ) : null}
      </div>
    </div>
  );
};
