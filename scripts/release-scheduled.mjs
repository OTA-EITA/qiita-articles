// Makes approved articles public when their time comes.
// schedule.json maps an article file in public/ to an ISO 8601 date-time;
// only articles the author has reviewed are listed there.
import { readFileSync, writeFileSync } from "node:fs";
import process from "node:process";

const schedule = JSON.parse(readFileSync("schedule.json", "utf8"));
const now = new Date(process.env.NOW ?? Date.now());
let released = 0;

for (const [file, at] of Object.entries(schedule)) {
  const when = new Date(at);
  if (Number.isNaN(when.getTime()))
    throw new Error(`${file}: invalid date "${at}"`);
  if (when > now) continue;
  const path = `public/${file}`;
  const src = readFileSync(path, "utf8");
  if (!/^private: true$/m.test(src)) continue; // already public
  writeFileSync(path, src.replace(/^private: true$/m, "private: false"));
  process.stdout.write(`released ${file} (scheduled ${at})\n`);
  released++;
}
process.stdout.write(`${String(released)} article(s) released\n`);
