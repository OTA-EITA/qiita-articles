#!/usr/bin/env bash
# Java4Shell（CVE-2026-114938）の条件がこのマシンでそろうかを調べる。
# 脆弱性を突く処理は実行しない。CPU の機能と Java の版・フラグを読むだけ。
set -u
echo "## runner: ${RUNNER_OS:-?} ${RUNNER_ARCH:-?} ${ImageOS:-} ${ImageVersion:-}"
if [ -r /proc/cpuinfo ]; then
  echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //')"
  flags=$(grep -m1 '^flags' /proc/cpuinfo)
  for f in avx512vbmi avx512bw bmi2; do
    if grep -qw "$f" <<<"$flags"; then echo "flag $f: yes"; else echo "flag $f: no"; fi
  done
fi
for v in $(env | grep -o '^JAVA_HOME_[0-9]*_[A-Za-z0-9]*' | sort -u); do
  home="${!v}"
  java="$home/bin/java"
  [ -x "$java" ] || java="$home/bin/java.exe"
  [ -x "$java" ] || continue
  ver=$("$java" -XshowSettings:properties -version 2>&1 | grep -m1 'java.runtime.version' | awk -F= '{print $2}' | tr -d ' ')
  vendor=$("$java" -XshowSettings:properties -version 2>&1 | grep -m1 'java.vendor = ' | cut -d= -f2- | sed 's/^ //')
  intr=$("$java" -XX:+PrintFlagsFinal -version 2>/dev/null | awk '$2=="UseBASE64Intrinsics"{print $4}')
  avx=$("$java" -XX:+PrintFlagsFinal -version 2>/dev/null | awk '$2=="UseAVX"{print $4}')
  feats=$("$java" -Xlog:os+cpu=info -version 2>&1 | grep -o -E 'avx512_vbmi\b|avx512bw|bmi2' | sort -u | tr '\n' ' ')
  echo "java $v: $ver ($vendor) UseBASE64Intrinsics=$intr UseAVX=$avx jvm-sees=[$feats]"
done
