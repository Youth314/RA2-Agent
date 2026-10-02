#!/usr/bin/env bash
# Build the pinned, behavior-unmodified ra2yrcpp baseline inside the workspace.
# Sources/submodules and APT tools must be prepared separately with approval.
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
task_root="${ENGINE_BUILD_ROOT:-$project_dir/.agents/tmp/engine-build}"
task_jobs="${ENGINE_BUILD_JOBS:-4}"
task_source="$task_root/sources/ra2yrcpp"
task_revision=ee215f5a01f709c52b1fe4dd333d16cbe5d5f146

if [[ ! "$task_jobs" =~ ^[1-9][0-9]*$ ]]; then
    echo 'ENGINE_BUILD_JOBS must be a positive integer.' >&2
    exit 1
fi
for task_tool in cmake git rg protoc i686-w64-mingw32-g++ i686-w64-mingw32-ar i686-w64-mingw32-objdump python3; do
    command -v "$task_tool" >/dev/null
done
if [[ "$(git -C "$task_source" rev-parse HEAD)" != "$task_revision" ]]; then
    echo 'Unexpected source revision; prepare the pinned baseline first.' >&2
    exit 1
fi
if [[ -n "$(git -C "$task_source" status --porcelain --untracked-files=all)" ]]; then
    echo 'Baseline sources/submodules must be clean.' >&2
    exit 1
fi
if git -C "$task_source" submodule status --recursive | rg -q '^[+U-]'; then
    echo 'Submodules must be checked out at their pinned revisions.' >&2
    exit 1
fi
if [[ "$(protoc --version)" != 'libprotoc 3.21.12' ]]; then
    echo 'This baseline recipe requires protoc 3.21.12.' >&2
    exit 1
fi

mkdir -p "$task_root/build" "$task_root/prefix/runtime" "$task_root/artifacts/baseline" "$task_root/logs"
task_toolchain="$task_source/toolchains/mingw-w64-i686.cmake"
task_gcc_runtime="$(dirname "$(i686-w64-mingw32-g++ -print-file-name=libgcc_s_dw2-1.dll)")"
task_pthread_source=/usr/i686-w64-mingw32/lib/libwinpthread.a
task_pthread_copy="$task_root/prefix/runtime/libwinpthread.a"

# --whole-archive would also copy winpthread's VERSIONINFO into our DLL.
# Remove only the resource member from a project-local copy of the archive.
cp "$task_pthread_source" "$task_pthread_copy"
i686-w64-mingw32-ar d "$task_pthread_copy" version.o

run_step() {
    local task_step="$1"
    shift
    printf '%q ' "$@" > "$task_root/logs/$task_step.command"
    printf '\n' >> "$task_root/logs/$task_step.command"
    if ! "$@" > "$task_root/logs/$task_step.log" 2>&1; then
        tail -60 "$task_root/logs/$task_step.log" >&2
        return 1
    fi
    echo "$task_step: complete"
}

run_step protobuf-configure cmake -S "$task_source/3rdparty/protobuf" \
    -B "$task_root/build/protobuf-i686" --toolchain "$task_toolchain" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$task_root/prefix/i686" \
    -Dprotobuf_BUILD_TESTS=OFF -Dprotobuf_BUILD_PROTOC_BINARIES=OFF \
    -Dprotobuf_BUILD_LIBPROTOC=OFF -Dprotobuf_BUILD_SHARED_LIBS=OFF \
    -Dprotobuf_WITH_ZLIB=ON -DZLIB_LIBRARY=/usr/i686-w64-mingw32/lib/libz.a \
    -DZLIB_INCLUDE_DIR=/usr/i686-w64-mingw32/include
run_step protobuf-build cmake --build "$task_root/build/protobuf-i686" \
    --target libprotobuf --parallel "$task_jobs"

# Upstream FetchContent obtains pinned GoogleTest even with BUILD_TESTS=OFF.
run_step ra2yrcpp-configure cmake -S "$task_source" \
    -B "$task_root/build/ra2yrcpp-i686" --toolchain "$task_toolchain" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$task_root/prefix/ra2yrcpp" \
    -DRA2YRCPP_VERSION=0.01-ee215f5-local-baseline -DRA2YRCPP_BUILD_TESTS=OFF \
    -DRA2YRCPP_BUILD_CLI_TOOL=OFF -DPROTOC_PATH="$(command -v protoc)" \
    -DPROTO_LIB="$task_root/build/protobuf-i686/libprotobuf.a" \
    -DZLIB_LIBRARY=/usr/i686-w64-mingw32/lib/libz.a \
    -DZLIB_INCLUDE_DIR=/usr/i686-w64-mingw32/include \
    -DCMAKE_INCLUDE_PATH="$task_gcc_runtime" \
    -DCMAKE_SHARED_LINKER_FLAGS="-L$task_root/prefix/runtime"
run_step ra2yrcpp-build cmake --build "$task_root/build/ra2yrcpp-i686" \
    --target ra2yrcpp_dll --parallel "$task_jobs"

cp "$task_root/build/ra2yrcpp-i686/bin/libra2yrcpp.dll" "$task_root/artifacts/baseline/libra2yrcpp.dll"
python3 - "$task_root" "$task_pthread_source" <<'PY'
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
source = root / 'sources/ra2yrcpp'
dll = root / 'artifacts/baseline/libra2yrcpp.dll'
blob = dll.read_bytes()
pe = struct.unpack_from('<I', blob, 0x3C)[0]
if blob[:2] != b'MZ' or blob[pe:pe+4] != b'PE\0\0':
    raise SystemExit('Not a PE file')
if struct.unpack_from('<H', blob, pe+4)[0] != 0x14C:
    raise SystemExit('Not Intel i386')
if struct.unpack_from('<H', blob, pe+24)[0] != 0x10B:
    raise SystemExit('Not PE32')
if not struct.unpack_from('<H', blob, pe+22)[0] & 0x2000:
    raise SystemExit('PE is not marked as a DLL')

def output(*args):
    return subprocess.check_output(args, text=True).strip()

details = output('i686-w64-mingw32-objdump', '-p', str(dll))
sections = output('i686-w64-mingw32-objdump', '-h', str(dll))
imports = re.findall(r'DLL Name:\s*(\S+)', details)
expected = {'WS2_32.DLL', 'WSOCK32.DLL', 'KERNEL32.DLL', 'MSVCRT.DLL'}
if {name.upper() for name in imports} != expected:
    raise SystemExit(f'Unexpected imports: {imports}')
exports = ['ExeRun', 'ExitGameLoop', 'GameLoopBegin', 'TunnelRecvFrom',
           'TunnelSendTo', 'UpdateLoadProgress', 'init_iservice']
if '.syhks00' not in sections or any(not re.search(r'\b' + name + r'\b', details) for name in exports):
    raise SystemExit('Missing hook section/export')
resources = details.split('The .rsrc Resource Directory section:')[-1]
if len(re.findall(r'Leaf: Addr:', resources)) != 1:
    raise SystemExit('Expected a single version resource after winpthread adaptation')
for label, text in [('pe-imports-exports', details), ('pe-sections', sections)]:
    (root / 'logs' / f'{label}.txt').write_text(text + '\n')

manifest = {
    'source_revision': output('git', '-C', str(source), 'rev-parse', 'HEAD'),
    'source_status': output('git', '-C', str(source), 'status', '--porcelain'),
    'submodules': output('git', '-C', str(source), 'submodule', 'status', '--recursive').splitlines(),
    'cmake': output('cmake', '--version').splitlines()[0],
    'compiler': output('i686-w64-mingw32-g++', '--version').splitlines()[0],
    'protoc': output('protoc', '--version'),
    'sha256': hashlib.sha256(blob).hexdigest(),
    'size_bytes': len(blob),
    'system_winpthread_sha256': hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest(),
    'local_winpthread_sha256': hashlib.sha256((root / 'prefix/runtime/libwinpthread.a').read_bytes()).hexdigest(),
    'architecture': 'PE32 Intel i386 DLL',
    'imports': imports,
    'exports_checked': exports,
    'game_loaded': False,
}
(root / 'artifacts/baseline/manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(f'Baseline DLL: {dll}\nSHA-256: {manifest["sha256"]}')
PY
