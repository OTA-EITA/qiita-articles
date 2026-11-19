#!/usr/bin/env node
// HTML のスライドを同じ物差しで数える（Node 22 以降と Chrome。依存なし）。
//   node measure-html.mjs <名前> <deck.html> [スライドの CSS セレクタ（既定 section.slide）]
// 1 枚ごとに: 文字数、書体、太字・色で強調した要素の数、角丸か影の付いた「箱」の数、絵文字の数、アイコン（svg / img の小さいもの）の数。

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [name, file, sel = 'section.slide'] = process.argv.slice(2);
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const profile = mkdtempSync(join(tmpdir(), 'measure-'));
const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', '--hide-scrollbars', `--user-data-dir=${profile}`, '--remote-debugging-port=0', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
const wsUrl = await new Promise(ok => { let b = ''; proc.stderr.on('data', d => { b += d; const m = b.match(/ws:\/\/\S+/); if (m) ok(m[0]); }); });
const ws = new WebSocket(wsUrl); await new Promise(ok => ws.onopen = ok);
let id = 0; const wait = new Map(); const events = [];
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id) { wait.get(m.id)?.(m); wait.delete(m.id); } else events.push(m); };
const send = (method, params = {}, sessionId) => new Promise(ok => { const n = ++id; wait.set(n, ok); ws.send(JSON.stringify({ id: n, method, params, sessionId })); });
const { result: { targetId } } = await send('Target.createTarget', { url: 'about:blank' });
const { result: { sessionId } } = await send('Target.attachToTarget', { targetId, flatten: true });
const page = (m, p) => send(m, p, sessionId);
await page('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
await page('Page.enable');
await page('Page.navigate', { url: pathToFileURL(resolve(file)).href });
await new Promise(r => setTimeout(r, 4000));

const expr = `(async () => {
  await document.fonts.ready;
  const emojiRe = /\\p{Extended_Pictographic}/gu;
  const slides = [...document.querySelectorAll(${JSON.stringify(sel)})];
  return slides.map((s, i) => {
    // 測るあいだだけ、その 1 枚を見える状態にする
    s.style.setProperty('visibility', 'visible', 'important'); s.style.setProperty('opacity', '1', 'important');
    s.style.setProperty('display', getComputedStyle(s).display === 'none' ? 'block' : getComputedStyle(s).display, 'important');
    const base = s.getBoundingClientRect(), area = base.width * base.height;
    let chars = 0, emoji = 0, emph = 0, boxes = 0, icons = 0; const fonts = new Set();
    const bodyW = Number(getComputedStyle(s).fontWeight);
    s.querySelectorAll('*').forEach(el => {
      const cs = getComputedStyle(el);
      if (cs.display === 'none') return;
      const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('');
      const t = own.replace(/\\s/g, '');
      if (t) {
        chars += t.length; emoji += (t.match(emojiRe) || []).length;
        fonts.add(cs.fontFamily.split(',')[0].replace(/["']/g, '').trim());
        const fs = parseFloat(cs.fontSize) * 1920 / base.width;
        if (!el.matches('h1,h2,h3,h4') && fs < 48 && Number(cs.fontWeight) >= 700) emph++;
      }
      const r = el.getBoundingClientRect(), a = r.width * r.height / area;
      const filled = cs.backgroundColor !== 'rgba(0, 0, 0, 0)' || cs.borderStyle !== 'none';
      if (a > 0.01 && a < 0.5 && filled && (parseFloat(cs.borderTopLeftRadius) >= 6 || cs.boxShadow !== 'none')) boxes++;
      if ((el.tagName === 'svg' || el.tagName === 'IMG') && r.width < base.width * 0.08 && r.width > 0) icons++;
    });
    s.style.removeProperty('visibility'); s.style.removeProperty('opacity'); s.style.removeProperty('display');
    return { n: i + 1, chars, emoji, emph, boxes, icons, fonts: [...fonts] };
  });
})()`;
const { result } = await page('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
const slides = result.result.value;
const med = a => { const b = [...a].sort((x, y) => x - y); return b[Math.floor(b.length / 2)]; };
const sum = k => slides.reduce((t, s) => t + s[k], 0);
const fonts = new Set(slides.flatMap(s => s.fonts).filter(f => !/mono|Menlo|Courier|Consolas/i.test(f)));
console.log(JSON.stringify({
  name, slides: slides.length, chars_median: med(slides.map(s => s.chars)), chars_max: Math.max(...slides.map(s => s.chars)),
  over150: slides.filter(s => s.chars > 150).length, fonts: [...fonts], emoji: sum('emoji'), emph: sum('emph'),
  boxes: sum('boxes'), slides_with_boxes: slides.filter(s => s.boxes > 0).length, icons: sum('icons'), per_slide: slides,
}));
await send('Browser.close').catch(() => {}); proc.kill(); setTimeout(() => { rmSync(profile, { recursive: true, force: true, maxRetries: 5 }); process.exit(0); }, 500);
