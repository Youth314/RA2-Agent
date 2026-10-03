#!/usr/bin/env python3
"""Build Guard, Stop, Target or Attack v1 using clean baseline dependencies.

No installation, network access, game launch or DLL deployment. See
engine/ra2yrcpp/README.md and the project's Guard validation record.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
REVISION = "ee215f5a01f709c52b1fe4dd333d16cbe5d5f146"
PROTOCOL_REVISION = "0ad72455bcdcf5626d0e17c3311ea82556da2ad3"
PROTOCOL = Path("src/protocol/ra2yrproto")


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def main():
    root = Path(os.environ.get("ENGINE_BUILD_ROOT", PROJECT / ".agents/tmp/engine-build")).resolve()
    feature = os.environ.get("ENGINE_FEATURE", "guard")
    require(feature in ("guard", "stop", "target", "attack"),
            "ENGINE_FEATURE must be guard, stop, target or attack")
    jobs = os.environ.get("ENGINE_BUILD_JOBS", "4")
    require(re.fullmatch(r"[1-9][0-9]*", jobs), "ENGINE_BUILD_JOBS must be positive")
    baseline = root / "sources/ra2yrcpp"
    source = root / f"sources/ra2yrcpp-{feature}"
    patches = PROJECT / "engine/ra2yrcpp/patches"
    specs = [(Path("."), patches / f"{feature}-v1-engine.patch", REVISION),
             (PROTOCOL, patches / f"{feature}-v1-protocol.patch", PROTOCOL_REVISION)]
    for directory, _, revision in specs:
        require(output("git", "-C", str(baseline / directory), "rev-parse", "HEAD") == revision,
                "Unexpected baseline revision")
    require(not output("git", "-C", str(baseline), "status", "--porcelain", "--untracked-files=all"),
            "Baseline must remain clean")
    require(not re.search(r"^[+U-]", output("git", "-C", str(baseline), "submodule", "status", "--recursive"), re.M),
            "Baseline submodules are not pinned")
    require(output("protoc", "--version") == "libprotoc 3.21.12", "protoc 3.21.12 required")
    dependencies = [root / "build/protobuf-i686/libprotobuf.a",
                    root / "prefix/runtime/libwinpthread.a",
                    root / "build/ra2yrcpp-i686/_deps/googletest-src/CMakeLists.txt",
                    root / "artifacts/baseline/manifest.json"]
    require(all(p.is_file() for p in dependencies), "Run the baseline recipe first")
    if not source.exists():
        print(f"Copying pinned baseline to {source}", flush=True)
        shutil.copytree(baseline, source)
        for directory, patch, _ in specs:
            subprocess.run(["git", "-C", str(source / directory), "apply", "--check", str(patch)], check=True)
            subprocess.run(["git", "-C", str(source / directory), "apply", str(patch)], check=True)
        if feature in ("target", "attack"):
            # Track the new header as intent-to-add so diff includes its patch
            # while the staged diff remains empty. No commit is created.
            subprocess.run(["git", "-C", str(source), "add", "--intent-to-add", "--",
                            "src/ra2/target_observation.hpp"], check=True)
            if feature == "attack":
                subprocess.run(["git", "-C", str(source), "add", "--intent-to-add", "--",
                                "src/ra2/attack_policy.hpp", "src/ra2/attack_target.hpp"], check=True)
    for directory, patch, revision in specs:
        repo = source / directory
        require(output("git", "-C", str(repo), "rev-parse", "HEAD") == revision,
                "Feature source revision changed")
        diff = subprocess.check_output(["git", "-C", str(repo), "diff", "--ignore-submodules=all"])
        require(diff == patch.read_bytes(), f"Feature diff differs from {patch}; reconcile explicitly")
        require(not output("git", "-C", str(repo), "ls-files", "--others", "--exclude-standard"),
                "Unrecognized untracked feature source files")
        require(not output("git", "-C", str(repo), "diff", "--cached"), "Unexpected staged source changes")
        allowed = ({"src/commands_game.cpp", "src/hooks_yr.cpp", "src/ra2/state_parser.cpp",
                    "src/protocol/ra2yrproto"} if directory == Path(".") else
                   {"ra2yrproto/commands_game.proto", "ra2yrproto/ra2yr.proto"})
        if feature in ("target", "attack") and directory == Path("."):
            allowed.add("src/ra2/target_observation.hpp")
            if feature == "attack":
                allowed.update({"src/ra2/abi.hpp", "src/ra2/attack_policy.hpp", "src/ra2/attack_target.hpp"})
        status = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
        require(all(line[3:] in allowed for line in status.splitlines()),
                "Unexpected modified files/submodules in feature source")
    build = root / f"build/ra2yrcpp-{feature}-i686"
    logs = root / "logs"
    artifact = root / f"artifacts/{feature}-v1"
    logs.mkdir(parents=True, exist_ok=True)
    artifact.mkdir(parents=True, exist_ok=True)

    def run_step(name, args):
        (logs / f"{name}.command.json").write_text(json.dumps(args, indent=2) + "\n")
        with (logs / f"{name}.log").open("w") as log:
            result = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            print("\n".join((logs / f"{name}.log").read_text().splitlines()[-60:]))
            raise SystemExit(result.returncode)
        print(f"{name}: complete", flush=True)

    runtime = str(Path(output("i686-w64-mingw32-g++", "-print-file-name=libgcc_s_dw2-1.dll")).parent)
    configure_args = ["cmake", "-S", str(source), "-B", str(build),
             "--toolchain", str(source / "toolchains/mingw-w64-i686.cmake"),
             "-DCMAKE_BUILD_TYPE=Release", f"-DRA2YRCPP_VERSION=0.01-ee215f5-{feature}-v1",
             "-DRA2YRCPP_BUILD_TESTS=OFF", "-DRA2YRCPP_BUILD_CLI_TOOL=OFF",
             f"-DPROTOC_PATH={shutil.which('protoc')}",
             f"-DPROTO_LIB={root / 'build/protobuf-i686/libprotobuf.a'}",
             "-DZLIB_LIBRARY=/usr/i686-w64-mingw32/lib/libz.a",
             "-DZLIB_INCLUDE_DIR=/usr/i686-w64-mingw32/include",
             f"-DCMAKE_INCLUDE_PATH={runtime}",
             f"-DCMAKE_SHARED_LINKER_FLAGS=-L{root / 'prefix/runtime'}",
             f"-DFETCHCONTENT_SOURCE_DIR_GOOGLETEST={root / 'build/ra2yrcpp-i686/_deps/googletest-src'}"]
    if os.environ.get("ENGINE_RESUME_BUILD") == "1":
        cache = build / "CMakeCache.txt"
        require(cache.is_file(), "Resume requires an existing configured feature build")
        contents = cache.read_text()
        require(f"CMAKE_HOME_DIRECTORY:INTERNAL={source}\n" in contents
                and re.search(r"^RA2YRCPP_VERSION:(?:STRING|UNINITIALIZED)="
                              + re.escape(f"0.01-ee215f5-{feature}-v1") + r"$", contents, re.M),
                "Resume cache differs from this feature; configure normally")
        print(f"{feature}-configure: reusing verified feature cache", flush=True)
    else:
        run_step(f"{feature}-configure", configure_args)
    run_step(f"{feature}-build", ["cmake", "--build", str(build), "--target", "ra2yrcpp_dll", "--parallel", jobs])
    dll = artifact / "libra2yrcpp.dll"
    shutil.copyfile(build / "bin/libra2yrcpp.dll", dll)
    blob = dll.read_bytes()
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    require(blob[:2] == b"MZ" and blob[pe:pe+4] == b"PE\0\0", "Invalid PE")
    require(struct.unpack_from("<H", blob, pe+4)[0] == 0x14C
            and struct.unpack_from("<H", blob, pe+24)[0] == 0x10B
            and struct.unpack_from("<H", blob, pe+22)[0] & 0x2000, "Expected i386 PE32 DLL")
    details = output("i686-w64-mingw32-objdump", "-p", str(dll))
    sections = output("i686-w64-mingw32-objdump", "-h", str(dll))
    imports = re.findall(r"DLL Name:\s*(\S+)", details)
    require({name.upper() for name in imports} == {"WS2_32.DLL", "WSOCK32.DLL", "KERNEL32.DLL", "MSVCRT.DLL"},
            f"Unexpected runtime imports: {imports}")
    exports = ["ExeRun", "ExitGameLoop", "GameLoopBegin", "TunnelRecvFrom",
               "TunnelSendTo", "UpdateLoadProgress", "init_iservice"]
    require(".syhks00" in sections and all(re.search(r"\b" + name + r"\b", details) for name in exports),
            "Missing hook section or exports")
    require(len(re.findall(r"Leaf: Addr:", details.split("The .rsrc Resource Directory section:")[-1])) == 1,
            "Unexpected resource count")
    (logs / f"{feature}-pe-imports-exports.txt").write_text(details + "\n")
    (logs / f"{feature}-pe-sections.txt").write_text(sections + "\n")
    manifest = dict(source_revision=REVISION, protocol_revision=PROTOCOL_REVISION,
                    patches={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for _, p, _ in specs},
                    sha256=hashlib.sha256(blob).hexdigest(), size_bytes=len(blob),
                    architecture="PE32 Intel i386 DLL", imports=imports,
                    exports_checked=exports, game_loaded=False,
                    compiler=output("i686-w64-mingw32-g++", "--version").splitlines()[0],
                    protoc=output("protoc", "--version"))
    (artifact / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{feature} DLL: {dll}\nSHA-256: {manifest['sha256']}")


if __name__ == "__main__":
    main()
