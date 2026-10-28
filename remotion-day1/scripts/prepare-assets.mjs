// Reuse existing repository font assets; no Google Fonts/network at render time.
import { mkdirSync, copyFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const output = new URL("../public/fonts/", import.meta.url);
mkdirSync(output, { recursive: true });
for (const [source, target] of [
  ["Inter.ttf", "Inter.ttf"],
  ["BarlowCondensed-SemiBold.ttf", "BarlowCondensed.ttf"],
]) {
  copyFileSync(
    fileURLToPath(new URL(`../../day2/assets/${source}`, import.meta.url)),
    fileURLToPath(new URL(target, output)),
  );
}
