#!/usr/bin/env bash
# NGINX2Shell（CVE-2026-123007）の対象かを、イメージの中の nginx の版で調べる。
# 当たる版: 1.9.5〜1.31.8（nginx.org の security advisories）。修正版: 1.31.9 以降、1.30.7 以降。
# 脆弱性を突く処理は実行しない。nginx -V の出力を読むだけ。
set -u
verdict() {
  local v=$1
  python3 - "$v" <<'PY'
import sys
v=tuple(int(x) for x in sys.argv[1].split('.'))
fixed = (v[:2]==(1,30) and v>=(1,30,7)) or v>=(1,31,9)
bad = (1,9,5) <= v <= (1,31,8) and not fixed
print('当たる' if bad else '当たらない')
PY
}
for img in "$@"; do
  out=$(docker run --rm --entrypoint sh "$img" -c 'for n in nginx /usr/local/nginx/sbin/nginx /usr/sbin/nginx; do command -v $n >/dev/null 2>&1 && { $n -V 2>&1; break; }; [ -x $n ] && { $n -V 2>&1; break; }; done' 2>&1)
  ver=$(grep -o -m1 -E 'nginx/[0-9]+\.[0-9]+\.[0-9]+' <<<"$out" | cut -d/ -f2)
  h2=$(grep -q -- '--with-http_v2_module' <<<"$out" && echo yes || echo no)
  created=$(docker image inspect "$img" --format '{{.Created}}' 2>/dev/null | cut -c1-10)
  if [ -n "$ver" ]; then echo "image $img: nginx $ver http_v2_module=$h2 created=$created => $(verdict "$ver")"; else echo "image $img: nginx の版を読めなかった"; fi
done
