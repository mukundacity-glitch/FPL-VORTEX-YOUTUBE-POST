import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  continueRender,
  delayRender,
  cancelRender,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Video } from "@remotion/media";
import type { RenderProps, ReviewShow } from "./types";
import { LegacyDay1Premium } from "./LegacyComposition";
import { AnimatedSquadPitch } from "./components/AnimatedSquadPitch";
import { PremiumFooter } from "./components/PremiumFooter";
import { SceneContent } from "./scenes/ReviewScenes";
import { normalizeForRender } from "./normalize";
import "./premium.css";
const labels: Record<string, string> = {
  opening: "THE TURNING POINT",
  highlights: "GAMEWEEK IN FOCUS",
  top: "TOP THREE PERFORMERS",
  worst: "THREE DECISION CHECKS",
  summary: "MY GAMEWEEK STORY",
  pitch: "THE FULL SQUAD",
  reviews: "STARTING XI REVIEW",
  bench: "BENCH & AVAILABILITY",
  closing: "THE NEXT STEP",
};
const Fonts: React.FC<{ css: string }> = ({ css }) => {
  const [handle] = useState(() => delayRender("Bundled broadcast fonts"));
  useEffect(() => {
    Promise.all([
      document.fonts.load("600 60px Barlow"),
      document.fonts.load("600 28px Inter"),
    ])
      .then(() => continueRender(handle))
      .catch(cancelRender);
  }, [handle]);
  return (
    <style>
      {css ||
        `@font-face{font-family:Inter;src:url('${staticFile("fonts/Inter.ttf")}')}@font-face{font-family:Barlow;src:url('${staticFile("fonts/BarlowCondensed.ttf")}')}`}
    </style>
  );
};
const Stadium: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill className="vx-stadium">
      <div
        className="vx-stadium-lights"
        style={{ translate: `${Math.sin(frame / fps / 9) * 45}px 0px` }}
      />
      <div className="vx-grain" />
      <div
        className="vx-light-beam"
        style={{ rotate: `${-15 + Math.sin(frame / fps / 12) * 5}deg` }}
      />
      <svg className="vx-bg-tactics" viewBox="0 0 1920 1080">
        <path
          d="M0 830Q450 300 1100 600T1920 180"
          stroke="#27fbb421"
          fill="none"
          strokeWidth="2"
          strokeDasharray="10 24"
          strokeDashoffset={-frame * 0.5}
        />
        <circle
          cx="600"
          cy="480"
          r={260 + Math.sin(frame / fps) * 5}
          stroke="#44bce410"
          fill="none"
        />
      </svg>
    </AbsoluteFill>
  );
};
const PitchTrack: React.FC<{ show: ReviewShow; start: number }> = ({
  show,
  start,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const time = start + frame / fps;
  const index = Math.max(
    0,
    show.sections.findIndex((s) => time >= s.start && time < s.end),
  );
  const section = show.sections[index];
  const own = new Set(show.package.players.map((p) => p.id));
  const players = show.players.filter((p) => own.has(p.id));
  const selected =
    ["reviews", "bench", "top", "worst"].includes(section.scene) &&
    own.has(section.player_id)
      ? section.player_id
      : undefined;
  return (
    <AnimatedSquadPitch
      formation={show.formation}
      startingXI={players.filter((p) => !p.isBench)}
      bench={players.filter((p) => p.isBench)}
      captain={show.accuracy.captain_id}
      viceCaptain={players.find((p) => p.isViceCaptain)?.id}
      points={show.accuracy.gw_points}
      selectedPlayer={selected}
      previousPlayer={show.sections[index - 1]?.player_id}
      selectionFrame={(time - section.start) * fps}
      entranceStart={time < 175 ? -100 : 175 - start}
    />
  );
};
const BroadcastHeader: React.FC<{ show: ReviewShow; start: number }> = ({
  show,
  start,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const time = start + frame / fps;
  const section =
    show.sections.find((s) => time >= s.start && time < s.end) ||
    show.sections[0];
  return (
    <header className="vx-header">
      <div className="vx-header-brand">
        FPL <em>VORTEX</em>
        <span>THE GAMEWEEK REVIEW</span>
      </div>
      <div className="vx-header-section">{labels[section.scene]}</div>
      <div className="vx-gw-pill">
        <i /> GW {String(show.review_gw).padStart(2, "0")} <span>FINAL</span>
      </div>
      {show.performer_scope.includes("Synthetic") ||
      show.performer_scope.includes("synthetic") ? (
        <div className="vx-sample">SYNTHETIC PREVIEW · NOT LIVE FPL DATA</div>
      ) : null}
    </header>
  );
};
const CaptionTrack: React.FC<{ show: ReviewShow; start: number }> = ({
  show,
  start,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const time = start + frame / fps;
  const active = show.words.findIndex(
    (w) => time >= w.start && time < w.start + w.duration,
  );
  if (active < 0) return null;
  const current = show.words[active];
  const words = show.words.filter((w) => w.section_id === current.section_id);
  const index = words.indexOf(current);
  const chunk = words.slice(
    Math.floor(index / 5) * 5,
    Math.floor(index / 5) * 5 + 5,
  );
  return (
    <div className="vx-captions">
      {chunk.map((w, i) => (
        <span key={i} className={w === current ? "active" : ""}>
          {w.text}
        </span>
      ))}
    </div>
  );
};
const Playhead: React.FC<{ show: ReviewShow; start: number }> = ({
  show,
  start,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div
      className="vx-progress"
      style={{
        width: `${Math.min(1, (start + frame / fps) / show.duration) * 100}%`,
      }}
    />
  );
};
export const Day1Premium: React.FC<RenderProps> = (props) => {
  const { show, start, end, vertical, fontCss, popup } = props;
  const { width, height, fps } = useVideoConfig();
  if (!show || show.version !== "VORTEX-PITCH-REVIEW-2")
    return <LegacyDay1Premium {...props} />;
  const review = normalizeForRender(show as ReviewShow);
  return (
    <AbsoluteFill style={{ background: "#060b1e" }}>
      <Fonts css={fontCss} />
      <div
        className={`vx-broadcast ${vertical ? "vx-vertical" : ""}`}
        style={{
          width: 1920,
          height: 1080,
          scale: `${width / (vertical ? 1080 : 1920)} ${height / (vertical ? 1920 : 1080)}`,
        }}
      >
        <Stadium />
        <PitchTrack show={review} start={start} />
        {review.sections
          .filter((s) => s.end > start && s.start < end)
          .map((s) => (
            <Sequence
              key={s.id}
              name={`${labels[s.scene]} · ${s.title}`}
              from={Math.round((s.start - start) * fps)}
              durationInFrames={
                Math.round(s.end * fps) - Math.round(s.start * fps)
              }
              layout="none"
            >
              <SceneContent show={review} section={s} />
            </Sequence>
          ))}
        <BroadcastHeader show={review} start={start} />
        <CaptionTrack show={review} start={start} />
        <PremiumFooter
          logo={show.brand_logo}
          start={start}
          episode={`GW${show.review_gw} · REVIEW`}
        />
        {!vertical && popup
          ? popup.starts
              .filter((at) => at < end && at + popup.duration > start)
              .map((at) => (
                <Sequence
                  key={at}
                  name={`Original footer popup · ${at}s`}
                  from={Math.round((at - start) * fps)}
                  durationInFrames={Math.min(
                    Math.ceil(popup.duration * fps),
                    Math.round((end - at) * fps),
                  )}
                  layout="none"
                >
                  <div className="vx-footer-popup">
                    <Video
                      src={staticFile(popup.src)}
                      muted
                      objectFit="contain"
                      style={{ width: "100%", height: "100%" }}
                    />
                  </div>
                </Sequence>
              ))
          : null}
        <Playhead show={review} start={start} />
      </div>
    </AbsoluteFill>
  );
};
