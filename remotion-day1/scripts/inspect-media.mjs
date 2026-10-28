// Metadata preflight only. Production continues to mux/duck with its existing FFmpeg flow.
import { Input, ALL_FORMATS, FilePathSource } from "mediabunny";
const [path, expectedText] = process.argv.slice(2);
if (!path)
  throw new Error(
    "Usage: node scripts/inspect-media.mjs FILE [MINIMUM_DURATION_SECONDS]",
  );
const input = new Input({
  formats: ALL_FORMATS,
  source: new FilePathSource(path),
});
try {
  const duration = await input.computeDuration();
  if (!Number.isFinite(duration) || duration <= 0)
    throw new Error("Invalid media duration");
  const expected = Number(expectedText);
  if (expectedText && (!Number.isFinite(expected) || duration + 0.3 < expected))
    throw new Error(
      `Media is too short: ${duration.toFixed(3)}s; needs ${expected}s`,
    );
  process.stdout.write(
    JSON.stringify({ duration, checkedWith: "Mediabunny" }) + "\n",
  );
} finally {
  input.dispose();
}
