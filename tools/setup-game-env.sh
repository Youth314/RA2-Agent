#!/usr/bin/env bash
# 建立 RA2:YR 的游戏侧运行环境。
#
# 用法: setup-game-env.sh <源目录> <目标目录>
#
# 源目录应当是只读的原始安装（例如 Steam 的那份），永不修改。
# 目标目录是本脚本生成的可重建副本。
#
# 依赖的压缩包默认从 <仓库根>/.agents/tmp 读取，可用环境变量 RA2_DEPS_DIR 覆盖。
#
# MIX 文件用硬链接（游戏只读，不占额外空间）；其余文件真实复制
# （可执行文件与配置可能被就地修改，硬链接会连带改坏源文件）。
set -euo pipefail

SRC="${1:?用法: $0 <源目录> <目标目录>}"
DST="${2:?用法: $0 <源目录> <目标目录>}"
REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
T="${RA2_DEPS_DIR:-$REPO/.agents/tmp}"

[ -d "$SRC" ] || { echo "源目录不存在: $SRC" >&2; exit 1; }
for f in ra2yrcpp.zip yr-patches.zip libwinpthread.zip; do
  [ -f "$T/$f" ] || { echo "缺少 $T/$f" >&2; exit 1; }
done

# 从 zip 中提取指定条目，扁平化到目标目录
extract() {
  local zip="$1" dst="$2"; shift 2
  python3 - "$zip" "$dst" "$@" <<'PY'
import os, shutil, sys, zipfile
zf, dst, names = sys.argv[1], sys.argv[2], sys.argv[3:]
with zipfile.ZipFile(zf) as z:
    index = set(z.namelist())
    for n in names:
        if n not in index:
            raise SystemExit(f"{zf}: 找不到条目 {n}")
        with z.open(n) as src, open(os.path.join(dst, os.path.basename(n)), "wb") as out:
            shutil.copyfileobj(src, out)
        print(f"  提取 {os.path.basename(n)}")
PY
}

echo "源:   $SRC"
echo "目标: $DST"

rm -rf -- "$DST"
mkdir -p -- "$DST"

# 1) 非 MIX 内容真实复制（含子目录）
cd -- "$SRC"
for f in *; do
  [ -e "$f" ] || continue
  case "${f,,}" in
    *.mix) continue ;;
  esac
  cp -a -- "$f" "$DST/"
done

# 2) MIX 文件硬链接
n=0
for f in *.mix *.MIX; do
  [ -e "$f" ] || continue
  ln -- "$f" "$DST/$f"
  n=$((n + 1))
done
echo "硬链接 MIX: $n 个"

# 3) ra2yrcpp 运行时。libwinpthread-1.dll 未打进 release 包（许可证原因），
#    缺失会导致静默启动失败，见 shmocz/ra2yrcpp#8。
extract "$T/ra2yrcpp.zip" "$DST" libra2yrcpp.dll zlib1.dll ra2yrcppcli.exe
extract "$T/libwinpthread.zip" "$DST" libwinpthread-1.dll

# 4) CnCNet spawner（非 hardened 的 release 版）
extract "$T/yr-patches.zip" "$DST" \
  release/cncnet/gamemd-spawn.exe release/cncnet/cncnet5.dll

# 5) 配置
cat > "$DST/ra2yrcpp.json" <<'JSON'
{
  "port": 14521,
  "allowedHostsRegex": "0.0.0.0|127.0.0.1",
  "logFilename": "ra2yrcpp.log"
}
JSON

echo "完成: $DST"
