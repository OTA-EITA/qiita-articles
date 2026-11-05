import { createHmac } from 'node:crypto';
import { generateTotp, verifyTotp, totpAt } from './mamori/src/totp/totp.ts';

const secret = new TextEncoder().encode('12345678901234567890');

// 1. 1 つのコードが何秒間通るか (step 30 秒、window ±1)
const t0 = 1_700_000_010; // ステップの始まり (30 で割り切れる時刻)
const code = generateTotp(secret, t0).code;
const ok: number[] = [];
for (let dt = -120; dt <= 120; dt++) if (verifyTotp(secret, code, t0 + dt).ok) ok.push(dt);
console.log('t0 % 30 =', t0 % 30, 'code', code, 'accepted from', ok[0], 'to', ok.at(-1), 'seconds =', ok.length);

// 2. 同じコードの 2 回目
const first = verifyTotp(secret, code, t0);
const second = verifyTotp(secret, code, t0 + 5, { lastUsedCounter: first.counter! });
const secondNoMemory = verifyTotp(secret, code, t0 + 5);
console.log('first', first.ok, 'second with lastUsedCounter', second.ok, 'second without', secondNoMemory.ok);

// 3. 先頭の 0 を数値として扱ったら
const v = generateTotp(secret, 1111111109, { algorithm: 'SHA1', digits: 8, stepSeconds: 30 }).code;
console.log('RFC vector', v, 'as number', String(Number(v)), 'verify as number:', verifyTotp(secret, String(Number(v)), 1111111109, { options: { algorithm: 'SHA1', digits: 8, stepSeconds: 30 } }).ok);

// 4. カウンターを 32 ビットで書いたら (2603 年の RFC テストベクタ t=20000000000)
function wrong32(counter: number): string {
  const buf = Buffer.alloc(8); buf.writeUInt32BE(counter >>> 0, 4); // 上位 32 ビットを捨てる
  const h = createHmac('sha1', secret).update(buf).digest();
  const o = h[h.length - 1]! & 0xf;
  const b = ((h[o]! & 0x7f) << 24) | (h[o + 1]! << 16) | (h[o + 2]! << 8) | h[o + 3]!;
  return String(b % 1e8).padStart(8, '0');
}
for (const t of [2000000000, 20000000000]) {
  const c = Math.floor(t / 30);
  console.log('t', t, 'counter', c, '> 2^32?', c > 2 ** 32, 'right', totpAt(secret, c, { algorithm: 'SHA1', digits: 8, stepSeconds: 30 }), '32bit', wrong32(c));
}
