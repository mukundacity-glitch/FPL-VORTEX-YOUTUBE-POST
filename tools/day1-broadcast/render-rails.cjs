const path = require('node:path');
const fs = require('node:fs');
const {bundle} = require('@remotion/bundler');
const {openBrowser, selectComposition, renderStill} = require('@remotion/renderer');

async function main() {
  const manifest = process.argv[2];
  const scenes = JSON.parse(fs.readFileSync(manifest, 'utf8'));
  const output = path.dirname(manifest);
  const serveUrl = await bundle({entryPoint: path.join(__dirname, 'index.jsx'), onProgress: () => {}});
  const browser = await openBrowser('chrome', {
    browserExecutable: process.env.VORTEX_CHROMIUM || null,
  });
  try {
    for (const scene of scenes) {
      const inputProps = {scene};
      const composition = await selectComposition({
        serveUrl, id: 'BroadcastRails', inputProps, puppeteerInstance: browser,
      });
      for (const [label, frame] of [['settled', 35], ['entrance', 12]]) {
        await renderStill({
          serveUrl, composition, inputProps, frame, puppeteerInstance: browser,
          output: path.join(output, `rail-${scene.number}-${label}.png`),
        });
      }
    }
  } finally {
    await browser.close({silent: true});
    fs.rmSync(serveUrl, {recursive: true, force: true});
  }
}

main().catch(error => {console.error(error); process.exitCode = 1;});
