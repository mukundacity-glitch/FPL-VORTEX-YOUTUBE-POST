import React, { useState } from "react";
import { Img, staticFile } from "remotion";
export const mediaSrc = (src: string) =>
  /^(https?:|data:|blob:)/.test(src) ? src : staticFile(src.replace(/^\//, ""));
export const SafeImage: React.FC<{
  src?: string;
  className?: string;
  fallback: React.ReactNode;
}> = ({ src, className, fallback }) => {
  const [failed, setFailed] = useState(false);
  return src && !failed ? (
    <Img
      className={className}
      src={mediaSrc(src)}
      onError={() => setFailed(true)}
    />
  ) : (
    <>{fallback}</>
  );
};
export const Shirt: React.FC<{ color?: string; label?: string }> = ({
  color = "#53c4ef",
  label = "V",
}) => (
  <svg
    className="vx-shirt"
    viewBox="0 0 150 160"
    aria-label="Player image unavailable; shirt fallback"
  >
    <defs>
      <linearGradient id={`shirt-${label.replace(/\W/g, "")}`} x2=".9" y2="1">
        <stop stopColor={color} />
        <stop offset="1" stopColor="#132c47" />
      </linearGradient>
    </defs>
    <path
      d="m48 15 27 10 27-10 39 29-18 32-18-9v80H45V67l-18 9L9 44z"
      fill={color}
      stroke="#ffffff80"
      strokeWidth="2"
    />
    <path d="m48 15 27 10 27-10-8 20H56z" fill="#09152d" />
    <path d="M50 98h50M55 106h40" stroke="#ffffff35" strokeWidth="2" />
    <text
      x="75"
      y="87"
      textAnchor="middle"
      fill="white"
      fontSize="30"
      fontFamily="Arial"
      fontWeight="bold"
    >
      {label.slice(0, 3)}
    </text>
  </svg>
);
