import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { brand } from "../brand";
import { EventIcon } from "./EventIcon";
import { SafeImage } from "./Media";
export const PremiumFooter: React.FC<{
  logo?: string;
  start: number;
  episode: string;
}> = ({ logo, start, episode }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const global = frame + start * fps;
  return (
    <footer
      className="vx-footer"
      style={{
        opacity: interpolate(global, [0.25 * fps, 1.1 * fps], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }),
        translate: `0px ${interpolate(global, [0.25 * fps, 1.1 * fps], [15, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}px`,
      }}
    >
      <div>
        <SafeImage
          src={logo || brand.logo}
          className="vx-footer-logo"
          fallback={<span className="vx-logo-mark">V</span>}
        />
        <SafeImage
          src={brand.youtubeIcon}
          fallback={<EventIcon kind="youtube" size={30} />}
        />
        <b>{brand.channelName}</b>
        <span>{brand.youtubeHandle}</span>
      </div>
      <span className="vx-footer-episode">{episode}</span>
      <div>
        <SafeImage
          src={brand.xIcon}
          fallback={<EventIcon kind="x" size={24} />}
        />
        <b>{brand.xHandle}</b>
      </div>
    </footer>
  );
};
