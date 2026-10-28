import React from "react";
export type IconName =
  | "goal"
  | "assist"
  | "clean-sheet"
  | "saves"
  | "captain"
  | "bench-haul"
  | "injury"
  | "blank"
  | "points"
  | "bonus"
  | "clock"
  | "youtube"
  | "x"
  | "fixture";
export const EventIcon: React.FC<{ kind: IconName; size?: number }> = ({
  kind,
  size = 26,
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 32 32"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label={kind}
  >
    {kind === "goal" ? (
      <>
        <circle cx="16" cy="16" r="12" />
        <path d="m16 9 7 5-3 8h-8l-3-8zM16 4v5M4 13l5 1m14 0 5-1M9 26l3-4m8 0 3 4" />
      </>
    ) : null}
    {kind === "assist" ? (
      <>
        <path d="M4 24 24 7m-8 0h8v8M4 25h4" />
        <circle cx="7" cy="7" r="3" />
        <path strokeDasharray="2 4" d="M8 12v8" />
      </>
    ) : null}
    {kind === "clean-sheet" ? (
      <>
        <path d="m16 3 11 5v9c0 6-11 12-11 12S5 23 5 17V8z" />
        <path d="m10 16 4 4 8-9" />
      </>
    ) : null}
    {kind === "saves" ? (
      <path d="M9 28 5 18c-2-5 2-5 4-1V7c0-3 4-3 4 0v8V4c0-3 4-3 4 0v11V6c0-3 4-3 4 0v10-6c0-3 4-3 4 0v11l-5 7z" />
    ) : null}
    {kind === "captain" ? (
      <>
        <rect x="3" y="7" width="26" height="18" rx="5" />
        <path d="M21 12c-8-5-14 7-5 9h5" />
      </>
    ) : null}
    {kind === "bench-haul" ? (
      <>
        <path d="M4 16h24v6H4zM7 22v6m18-6v6M7 16V9h18v7" />
        <path d="m16 3-4 4h8z" />
      </>
    ) : null}
    {kind === "injury" ? (
      <>
        <path d="m16 3 14 25H2z" />
        <path d="M16 11v8m0 4v1" />
      </>
    ) : null}
    {kind === "blank" ? (
      <>
        <circle cx="16" cy="16" r="12" />
        <path d="M10 16h12" />
      </>
    ) : null}
    {kind === "bonus" || kind === "points" ? (
      <path d="m16 3 4 8 9 1-7 7 2 10-8-5-8 5 2-10-7-7 9-1z" />
    ) : null}
    {kind === "clock" ? (
      <>
        <circle cx="16" cy="16" r="12" />
        <path d="M16 8v9l6 3" />
      </>
    ) : null}
    {kind === "fixture" ? (
      <>
        <rect x="4" y="6" width="24" height="23" rx="4" />
        <path d="M10 3v7m12-7v7M4 14h24" />
      </>
    ) : null}
    {kind === "youtube" ? (
      <>
        <rect
          x="2"
          y="6"
          width="28"
          height="20"
          rx="6"
          fill="#ff3659"
          stroke="none"
        />
        <path d="m13 11 9 5-9 5z" fill="white" stroke="none" />
      </>
    ) : null}
    {kind === "x" ? <path d="M5 4h6l16 24h-6zM27 4 5 28" /> : null}
  </svg>
);
