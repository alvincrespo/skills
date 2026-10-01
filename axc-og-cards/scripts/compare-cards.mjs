#!/usr/bin/env node
// Compares two folders of card PNGs pixel by pixel.
//
//   node compare-cards.mjs <expectedDir> <actualDir>
//
// Compares decoded pixels, not file bytes: a different sharp or resvg version
// can change a PNG's bytes without changing the image. Exits 1 if any card is
// missing or differs.
import { readdir } from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";

const [expectedDir, actualDir] = process.argv.slice(2);
if (!expectedDir || !actualDir) {
  console.error("Usage: node compare-cards.mjs <expectedDir> <actualDir>");
  process.exit(2);
}

const pngs = async (dir) => (await readdir(dir)).filter((f) => f.endsWith(".png")).sort();
const [expected, actual] = await Promise.all([pngs(expectedDir), pngs(actualDir)]);

async function pixels(file) {
  const { data, info } = await sharp(file).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  return { data, width: info.width, height: info.height };
}

const problems = [];
for (const name of expected) {
  if (!actual.includes(name)) {
    problems.push(`${name}: missing from ${actualDir}`);
    continue;
  }
  const [a, b] = await Promise.all([pixels(path.join(expectedDir, name)), pixels(path.join(actualDir, name))]);
  if (a.width !== b.width || a.height !== b.height) {
    problems.push(`${name}: size ${a.width}x${a.height} vs ${b.width}x${b.height}`);
    continue;
  }
  let differing = 0;
  let maxDelta = 0;
  for (let i = 0; i < a.data.length; i++) {
    const d = Math.abs(a.data[i] - b.data[i]);
    if (d > 0) {
      differing++;
      if (d > maxDelta) maxDelta = d;
    }
  }
  if (differing > 0) problems.push(`${name}: ${differing} differing channel values (max delta ${maxDelta})`);
}
for (const name of actual) if (!expected.includes(name)) problems.push(`${name}: not in ${expectedDir}`);

if (problems.length > 0) {
  console.error(`${problems.length} of ${expected.length} cards differ:\n  ${problems.join("\n  ")}`);
  process.exit(1);
}
console.log(`All ${expected.length} cards match pixel for pixel.`);
