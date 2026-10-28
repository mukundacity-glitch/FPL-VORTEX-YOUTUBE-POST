export type Fixture = { opp: string; ha: string; gw: number };
export type Player = {
  id: number;
  name: string;
  photo?: string;
  badge?: string;
  team: string;
  team_name?: string;
  pos: string;
  points: number;
  status: string;
  bench: boolean;
  season_starts?: number;
  fixtures?: Fixture[];
  next_fixture?: Fixture | null;
};
export type Beat = {
  start: number;
  end: number;
  phrase: string;
  player_id: number;
  verdict: string;
  section: string;
  variant: number;
  transition: number;
};
export type Word = {
  text: string;
  start: number;
  duration: number;
  section_id: string;
};
export type Show = {
  duration: number;
  review_gw: number;
  preview_gw: number;
  brand_logo?: string;
  accuracy: { captain_points: number };
  package: { players: Player[] };
  beats: Beat[];
  words: Word[];
  highlights: { at: number; duration: number; word: string }[];
};
export type RenderProps = {
  show: Show | null;
  start: number;
  end: number;
  width: number;
  height: number;
  vertical: boolean;
  fontCss: string;
  verdictColors: Record<string, string>;
  popup: { src: string; duration: number; starts: number[] } | null;
};
