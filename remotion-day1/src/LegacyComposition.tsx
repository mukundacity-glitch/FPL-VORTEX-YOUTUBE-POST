import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  delayRender,
  continueRender,
  cancelRender,
} from "remotion";
import { Video } from "@remotion/media";
import { evidenceFor, sectionLabels } from "./model";
import type { Beat, Player, RenderProps, Show } from "./types";
import "./legacy.css";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const mediaSrc = (src: string) =>
  src.startsWith("runtime/") ? staticFile(src) : src;

const Fonts: React.FC<{ css: string }> = ({ css }) => {
  const [handle] = useState(() => delayRender("Day 1 bundled fonts"));
  useEffect(() => {
    Promise.all([
      document.fonts.load("600 80px Barlow"),
      document.fonts.load("600 30px Inter"),
    ])
      .then(() => continueRender(handle))
      .catch(cancelRender);
  }, [handle]);
  return <style>{css}</style>;
};

const PlayerCard: React.FC<{ show: Show; beat: Beat; player: Player }> = ({
  show,
  beat,
  player,
}) => {
  const evidence = evidenceFor(show, beat, player);
  const fixtures = player.fixtures ?? [];
  const fixture = fixtures[beat.variant % Math.max(1, fixtures.length)];
  return (
    <div className="hero-card" data-player-id={player.id}>
      <div className="card-light" />
      <div className="card-index">
        FPL VORTEX <span>PLAYER FILE</span>
      </div>
      {player.photo ? (
        <Img className="portrait" src={mediaSrc(player.photo)} />
      ) : (
        <div className="portrait-fallback">
          {player.name
            .split(/\s+/)
            .map((x) => x[0])
            .slice(0, 2)
            .join("")}
        </div>
      )}
      <div className="player-identity">
        <div
          className="player-name"
          style={{
            fontSize:
              player.name.length > 19 ? 42 : player.name.length > 13 ? 49 : 59,
          }}
        >
          {player.name}
        </div>
        <div className="identity-rule" />
        <div className="club">
          {player.badge ? <Img src={mediaSrc(player.badge)} /> : null}
          <span>{player.team_name || player.team}</span>
        </div>
        <div className="position">{player.pos}</div>
        <div
          className="verdict"
          style={{ fontSize: beat.verdict.length > 12 ? 19 : 24 }}
        >
          {beat.verdict}
        </div>
      </div>
      <div className="fixture-row">
        <span className="fixture-label">NEXT FIXTURE</span>
        <strong>{fixture ? `${fixture.opp} · ${fixture.ha}` : "—"}</strong>
        <span className="fixture-week">
          {fixture ? `GW${fixture.gw}` : "—"}
        </span>
      </div>
      <div className="evidence-panel">
        <span className="evidence-icon">{evidence[0]}</span>
        <div>
          <small>{evidence[1]}</small>
          <strong style={{ fontSize: evidence[2].length > 14 ? 34 : 60 }}>
            {evidence[2]}
          </strong>
        </div>
      </div>
    </div>
  );
};

const BeatSlide: React.FC<{
  show: Show;
  beat: Beat;
  index: number;
  colors: Record<string, string>;
}> = ({ show, beat, index, colors }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const player = show.package.players.find((p) => p.id === beat.player_id);
  if (!player)
    throw new Error(`Missing original Day 1 player ${beat.player_id}`);
  const transition = Math.max(1, Math.round(beat.transition * fps));
  const hold = Math.round(beat.end * fps) - Math.round(beat.start * fps);
  const accent =
    beat.section === "hook" && show.accuracy.captain_points <= 4
      ? "#ff7180"
      : colors[beat.verdict] || "#e7c68a";
  return (
    <AbsoluteFill
      className="slide"
      data-section={beat.section}
      style={
        {
          "--accent": accent,
          opacity: interpolate(
            frame,
            [0, transition, hold, hold + transition],
            [index === 0 ? 1 : 0, 1, 1, 0],
            clamp,
          ),
        } as React.CSSProperties
      }
    >
      <div
        className="editorial"
        style={{
          translate: `${interpolate(frame, [0, transition], [index === 0 ? 0 : 18, 0], { ...clamp, easing: Easing.bezier(0.16, 1, 0.3, 1) })}px 0px`,
        }}
      >
        <div className="kicker">
          <span />
          {sectionLabels[beat.section]}
        </div>
        <div className="title-rule" />
        <div
          className="headline"
          style={{
            fontSize:
              beat.phrase.length > 24
                ? 114
                : beat.phrase.length > 17
                  ? 134
                  : 160,
          }}
        >
          {beat.phrase}
        </div>
        <div className="decision-dots">
          {[1, 2, 3].map((n) => (
            <span
              key={n}
              className={beat.section === `decision_${n}` ? "on" : ""}
            />
          ))}
        </div>
      </div>
      <div
        className="card-motion"
        style={{
          translate: `0px ${interpolate(frame, [0, transition], [index === 0 ? 0 : 12, 0], clamp)}px`,
        }}
      >
        <PlayerCard show={show} beat={beat} player={player} />
      </div>
    </AbsoluteFill>
  );
};

const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill className="backdrop">
      <div
        className="halo"
        style={{ translate: `${Math.sin(frame / fps / 15) * 35}px 0px` }}
      />
      <div className="grid" />
      <div className="sweep" />
      <div className="edge-mark" />
    </AbsoluteFill>
  );
};

const CaptionTrack: React.FC<{ show: Show; start: number }> = ({
  show,
  start,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const time = start + frame / fps;
  let activeIndex = -1;
  for (let i = 0; i < show.words.length && show.words[i].start <= time; i++)
    activeIndex = i;
  const active = show.words[activeIndex];
  const sectionWords = active
    ? show.words.filter((w) => w.section_id === active.section_id)
    : [];
  const localIndex = active ? sectionWords.indexOf(active) : -1;
  const words = sectionWords.slice(
    Math.floor(localIndex / 5) * 5,
    Math.floor(localIndex / 5) * 5 + 5,
  );
  const next = show.words[activeIndex + 1];
  const visible =
    active && time < (next?.start ?? active.start + active.duration);
  const flash = show.highlights.find(
    (h) => time >= h.at && time < h.at + h.duration,
  );
  return (
    <>
      {flash ? <div className="word-flash">{flash.word}</div> : null}
      <div className="captions">
        {visible
          ? words.map((word, i) => (
              <span key={i} className={word === active ? "active" : ""}>
                {word.text}
              </span>
            ))
          : null}
      </div>
    </>
  );
};

const FooterPopup: React.FC<{ src: string }> = ({ src }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div
      className="footer-popup"
      style={{
        opacity: interpolate(frame, [0, Math.max(1, 0.2 * fps)], [0, 1], clamp),
        translate: `0px ${interpolate(frame, [0, Math.max(1, 0.3 * fps)], [10, 0], clamp)}px`,
      }}
    >
      <Video
        src={mediaSrc(src)}
        muted
        objectFit="contain"
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
};

const Progress: React.FC<{ show: Show; start: number }> = ({ show, start }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div
      className="progress"
      style={{
        width: `${Math.min(1, (start + frame / fps) / show.duration) * 100}%`,
      }}
    />
  );
};

export const LegacyDay1Premium: React.FC<RenderProps> = (props) => {
  const { show, start, end, vertical, fontCss, verdictColors, popup } = props;
  const { width, height, fps } = useVideoConfig();
  const logicalWidth = vertical ? 1080 : 1920;
  const logicalHeight = vertical ? 1920 : 1080;
  if (!show)
    return (
      <AbsoluteFill
        style={{
          background: "#080f1a",
          color: "#e7c68a",
          justifyContent: "center",
          alignItems: "center",
          fontFamily: "sans-serif",
          fontSize: 90,
        }}
      >
        FPL VORTEX
      </AbsoluteFill>
    );
  return (
    <AbsoluteFill>
      <Fonts css={fontCss} />
      <div
        className={`stage ${vertical ? "vertical" : ""}`}
        style={{
          width: logicalWidth,
          height: logicalHeight,
          scale: `${width / logicalWidth} ${height / logicalHeight}`,
        }}
      >
        <Background />
        <header className="brand-header">
          <div className="brand">
            {show.brand_logo ? (
              <Img src={mediaSrc(show.brand_logo)} />
            ) : (
              <span className="brand-monogram">V</span>
            )}
            <span>FPL VORTEX</span>
          </div>
          <div className="gw-badge">
            GAMEWEEK <b>{String(show.preview_gw).padStart(2, "0")}</b>
          </div>
        </header>
        {show.beats.map((beat, index) => {
          if (beat.end + beat.transition <= start || beat.start >= end)
            return null;
          const from = Math.round(beat.start * fps) - Math.round(start * fps);
          const frames =
            Math.round(beat.end * fps) -
            Math.round(beat.start * fps) +
            Math.round(beat.transition * fps);
          return (
            <Sequence
              key={index}
              name={`${sectionLabels[beat.section]} · ${beat.phrase}`}
              from={from}
              durationInFrames={frames}
              layout="none"
            >
              <BeatSlide
                show={show}
                beat={beat}
                index={index}
                colors={verdictColors}
              />
            </Sequence>
          );
        })}
        <CaptionTrack show={show} start={start} />
        <footer className="footer">
          <span>
            <b>FPL VORTEX</b>
            <i />
            @FPLVORTEX
          </span>
          <span>𝕏 @FPLVORTEXM</span>
        </footer>
        {!vertical && popup
          ? popup.starts
              .filter((at) => at < end && at + popup.duration > start)
              .map((at) => (
                <Sequence
                  key={at}
                  name={`Footer popup · ${at}s`}
                  from={Math.round((at - start) * fps)}
                  durationInFrames={Math.max(
                    1,
                    Math.min(
                      Math.ceil(popup.duration * fps),
                      Math.round((end - at) * fps),
                    ),
                  )}
                  layout="none"
                >
                  <FooterPopup src={popup.src} />
                </Sequence>
              ))
          : null}
        <Progress show={show} start={start} />
      </div>
    </AbsoluteFill>
  );
};
