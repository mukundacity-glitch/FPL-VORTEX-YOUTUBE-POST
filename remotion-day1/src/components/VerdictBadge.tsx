import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
export const verdictColor = (verdict: string) =>
  /START|BUY/.test(verdict)
    ? "#43fb8b"
    : /SELL|BENCH REGRET/.test(verdict)
      ? "#ff4863"
      : /WAIT|MONITOR/.test(verdict)
        ? "#ffcd19"
        : "#59d9ff";
export const VerdictBadge: React.FC<{ verdict: string; delay?: number }> = ({
  verdict,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  return (
    <div
      className="vx-verdict"
      style={{
        color: verdictColor(verdict),
        borderColor: verdictColor(verdict),
        opacity: interpolate(frame, [delay, delay + 12], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }),
      }}
    >
      <span />
      {verdict}
    </div>
  );
};
