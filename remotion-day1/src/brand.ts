// Existing project identities, centralized rather than guessed or derived.
export const brand = {
  channelName: "FPL VORTEX",
  youtubeHandle: "@FPLVORTEX",
  xHandle: "@FPLVORTEXM",
  logo: "", // public-relative asset; production prefers show.brand_logo from Drive.
  youtubeIcon: "", // Optional public-relative SVG; bundled icon is the fallback.
  xIcon: "",
};

// Match public/reference/player-card.jpg. All reference styling lives here/CSS vars.
export const cardTokens = {
  navy: "#0b1031",
  violet: "#9223ed",
  magenta: "#db12ed",
  cyan: "#00e3ec",
  green: "#43fb8b",
  amber: "#ffcd19",
  red: "#ff4863",
  white: "#f8f9ff",
  border: "#7779bd",
  radius: 30,
  rowRadius: 24,
};
export const clubColors: Record<string, string> = {
  ARS: "#ef4459",
  AVL: "#9b6cc8",
  BHA: "#3c9dff",
  CHE: "#3975fb",
  MCI: "#79ceef",
  MUN: "#f34a54",
  LEE: "#f5d357",
  EVE: "#4685ff",
  LIV: "#f34d60",
  NFO: "#ec4a5a",
  BOU: "#df4557",
  NEW: "#b5cad4",
};
