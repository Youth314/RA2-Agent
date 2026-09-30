"""单实例守卫补丁工具的测试。

全是离线假件：按真实布局造一个只含守卫的迷你 exe，不碰真文件。
"""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))

import patch_single_instance as psi  # noqa: E402


def fake_exe(payload_at_guard: bytes) -> bytes:
    """造一个守卫处放指定字节的迷你 exe。

    @param payload_at_guard: 放在守卫偏移处的字节。
    @returns: 文件内容。
    """
    data = bytearray(psi.GUARD_OFFSET + 0x40)
    data[:4] = b"MZ\x90\x00"
    data[psi.GUARD_OFFSET:psi.GUARD_OFFSET + len(payload_at_guard)] = payload_at_guard
    return bytes(data)


class PatchSingleInstanceTest(unittest.TestCase):
    """守卫的识别、补丁与还原。"""

    def setUp(self) -> None:
        """建一个临时目录。"""
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = pathlib.Path(self._dir.name) / "gamemd-spawn.exe"

    def write(self, content: bytes) -> None:
        """写入假 exe。

        @param content: 文件内容。
        """
        self.path.write_bytes(content)

    def test_recognizes_original(self) -> None:
        """原始字节应被认成 original。"""
        self.write(fake_exe(psi.GUARD_BYTES))
        self.assertEqual(psi.read_state(self.path), "original")

    def test_patch_changes_only_the_immediate(self) -> None:
        """补丁只动比较的立即数，其余字节一字不变。"""
        self.write(fake_exe(psi.GUARD_BYTES))
        self.assertEqual(psi.main(["--patch", str(self.path)]), 0)
        self.assertEqual(psi.read_state(self.path), "patched")
        got = self.path.read_bytes()
        self.assertEqual(got[psi.IMM_OFFSET:psi.IMM_OFFSET + 4], psi.IMM_PATCHED)
        self.assertEqual(got[:psi.IMM_OFFSET], fake_exe(psi.GUARD_BYTES)[:psi.IMM_OFFSET])
        self.assertEqual(got[psi.IMM_OFFSET + 4:], fake_exe(psi.GUARD_BYTES)[psi.IMM_OFFSET + 4:])

    def test_patch_is_idempotent(self) -> None:
        """重复打补丁不报错，也不改变结果。"""
        self.write(fake_exe(psi.GUARD_BYTES))
        psi.main(["--patch", str(self.path)])
        first = self.path.read_bytes()
        self.assertEqual(psi.main(["--patch", str(self.path)]), 0)
        self.assertEqual(self.path.read_bytes(), first)

    def test_restore_returns_the_original(self) -> None:
        """还原应恢复原始字节。"""
        original = fake_exe(psi.GUARD_BYTES)
        self.write(original)
        psi.main(["--patch", str(self.path)])
        self.assertEqual(psi.main(["--restore", str(self.path)]), 0)
        self.assertEqual(self.path.read_bytes(), original)

    def test_restore_without_backup_fails(self) -> None:
        """没有备份时还原应失败，而不是当成功。"""
        self.write(fake_exe(psi.GUARD_BYTES))
        self.assertEqual(psi.main(["--restore", str(self.path)]), 1)

    def test_refuses_unknown_bytes(self) -> None:
        """换一个 build 时拒绝改，而不是照偏移瞎写。"""
        self.write(fake_exe(b"\x99" * len(psi.GUARD_BYTES)))
        self.assertEqual(psi.read_state(self.path), "unknown")
        self.assertEqual(psi.main(["--patch", str(self.path)]), 2)
        self.assertEqual(psi.read_state(self.path), "unknown")

    def test_check_does_not_write(self) -> None:
        """--check 只报状态，不改文件。"""
        original = fake_exe(psi.GUARD_BYTES)
        self.write(original)
        self.assertEqual(psi.main(["--check", str(self.path)]), 0)
        self.assertEqual(self.path.read_bytes(), original)

    def test_missing_file_fails(self) -> None:
        """路径不存在时返回非零。"""
        missing = pathlib.Path(self._dir.name) / "nope.exe"
        self.assertEqual(psi.main(["--check", str(missing)]), 2)


if __name__ == "__main__":
    unittest.main()
