export type Fixture = {
  opp: string;
  ha: string;
  gw: number;
  difficulty?: number | null;
};
export type Player = {
  id: number;
  name: string;
  photo?: string;
  badge?: string;
  team: string;
  team_name?: string;
  pos: string;
  points: number | null;
  status: string;
  bench: boolean;
  season_starts?: number;
  fixtures?: Fixture[];
  next_fixture?: Fixture | null;
  minutes?: number | null;
  goals?: number | null;
  assists?: number | null;
  clean_sheets?: number | null;
  saves?: number | null;
  bonus?: number | null;
  price?: number | null;
  ownership?: number | null;
  multiplier?: number;
  squad_position?: number;
  captain?: boolean;
  vice?: boolean;
  news?: string;
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
  version?: string;
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
export type Action =
  | "goal"
  | "assist"
  | "clean-sheet"
  | "saves"
  | "captain"
  | "bench-haul"
  | "injury"
  | "blank"
  | "points";
export type ReviewPlayer = Player & {
  position: string;
  isCaptain: boolean;
  isViceCaptain: boolean;
  isBench: boolean;
  availability: string;
  status_reason: string;
  verdict: string;
  analysis: string;
  event_summary: string;
  action: Action;
};
export type ReviewSection = {
  id: string;
  scene: string;
  start: number;
  end: number;
  duration: number;
  player_id: number;
  title: string;
  text: string;
  verdict: string;
  action: Action;
};
export type Match = {
  id: number;
  home: string;
  away: string;
  home_score: number;
  away_score: number;
  story: string;
  player_ids: number[];
  goals?: number;
  assists?: number | null;
  clean_sheets?: number;
};
export type ReviewShow = Show & {
  players: ReviewPlayer[];
  sections: ReviewSection[];
  scenes: { id: string; start: number; end: number; duration: number }[];
  top_ids: number[];
  worst_ids: number[];
  performer_scope: string;
  formation: number[];
  matches: Match[];
  question: string;
  decisions: { player: Player; verdict: string }[];
  accuracy: Show["accuracy"] & {
    gw_points: number;
    captain_id: number;
    effective_captain_id: number;
    actual_bench_regret_id: number | null;
  };
  package: Show["package"] & {
    metrics: {
      gw_points: number;
      average_points?: number | null;
      transfer_cost?: number;
    };
  };
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
