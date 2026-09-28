#!/usr/bin/env bash
# 看门狗：监视指定进程，卡死或超时则强制结束，释放全屏。
# 用法: watchdog.sh <进程名> [最长秒数]
PROC="${1:?用法: $0 <进程名> [最长秒数]}"
MAX="${2:-150}"
TL=/mnt/c/Windows/System32/tasklist.exe
TK=/mnt/c/Windows/System32/taskkill.exe
for i in $(seq 1 "$MAX"); do
  sleep 1
  if ! "$TL" /FI "IMAGENAME eq $PROC" 2>/dev/null | grep -q "$PROC"; then
    echo "[${i}s] $PROC 已退出，看门狗结束"
    exit 0
  fi
  if [ $((i % 10)) -eq 0 ]; then
    if "$TL" /FI "IMAGENAME eq $PROC" /FI "STATUS eq NOT RESPONDING" 2>/dev/null | grep -q "$PROC"; then
      echo "[${i}s] $PROC 无响应，强制结束"
      "$TK" /IM "$PROC" /F >/dev/null 2>&1
      exit 0
    fi
  fi
done
echo "[${MAX}s] 超时，强制结束 $PROC"
"$TK" /IM "$PROC" /F >/dev/null 2>&1
