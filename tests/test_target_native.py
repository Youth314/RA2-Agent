"""直接编译 DLL 补丁中的纯目标过滤策略；不运行 Windows DLL。"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from ra2agent.engine.state import GameState

PROJECT = Path(__file__).resolve().parents[1]


class TestNativeTargetPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++")
        if compiler is None:
            raise unittest.SkipTest("Native target policy requires existing g++")
        patch = (PROJECT / "engine/ra2yrcpp/patches/target-v1-engine.patch").read_text()
        marker = "diff --git a/src/ra2/target_observation.hpp b/src/ra2/target_observation.hpp\n"
        section = patch.split(marker, 1)[1].split("\ndiff --git ", 1)[0]
        header = "\n".join(line[1:] for line in section.splitlines()
                           if line.startswith("+") and not line.startswith("+++")) + "\n"
        cls.temp = tempfile.TemporaryDirectory(prefix="ra2-target-policy-")
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        (root / "target_observation.hpp").write_text(header)
        cls.executable = root / "target-policy"
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-I", str(root), str(PROJECT / "tests/target_observation_native.cpp"),
                        "-o", str(cls.executable)], check=True, capture_output=True, text=True)

    def check_policy(self, number):
        result = subprocess.run([str(self.executable), str(number)],
                                check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout, "passed\n")

    def test_null_nonmember_and_removed_target(self):
        self.check_policy(1)

    def test_supported_and_unsupported_target_classes(self):
        self.check_policy(2)

    def test_foreign_or_ineligible_actor_never_exposes_target(self):
        self.check_policy(3)

    def test_current_identity_and_foreign_visibility_change(self):
        self.check_policy(4)

    def test_fog_cloak_disguise_and_unknown_visibility(self):
        self.check_policy(5)


class TestTargetSchema(unittest.TestCase):
    @unittest.skipUnless(shutil.which("protoc"), "Requires existing protoc")
    def test_protoc_wire_matches_python_and_retains_stop_guard(self):
        for code, label in ((1, "STATUS_UNOBSERVABLE"), (2, "STATUS_NONE"),
                            (3, "STATUS_OBJECT")):
            details = ("reference { m_id: -1 m_rtti: 52 } object_type: ABSTRACT_TYPE_INFANTRY "
                       "object_pointer: 177") if code == 3 else ""
            text = ("guard_interface_version: 1 stop_interface_version: 1 "
                    "target_observation_version: 1 objects { pointer_self: 161 "
                    f"actual_target {{ status: {label} {details} }} }}")
            with self.subTest(status=code):
                wire = subprocess.check_output(
                    ["protoc", "-I", str(PROJECT / "proto"),
                     "--encode=ra2yrproto.ra2yr.GameState", "ra2yrproto/ra2yr.proto"],
                    input=text.encode())
                parsed = GameState.parse(wire)
                self.assertEqual(parsed.guard_interface_version, 1)
                self.assertEqual(parsed.stop_interface_version, 1)
                self.assertEqual(parsed.target_observation_version, 1)
                self.assertEqual(parsed.object(161).actual_target.status, code)
                if code == 3:
                    self.assertEqual(parsed.object(161).actual_target.native_id, 0xFFFFFFFF)
                    self.assertEqual(parsed.object(161).actual_target.object_type, 15)


if __name__ == "__main__":
    unittest.main()
