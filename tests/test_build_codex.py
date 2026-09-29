"""`tools/build_codex.py` 的测试。只测纯函数。"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

spec = importlib.util.spec_from_file_location("build_codex", REPO / "tools" / "build_codex.py")
build_codex = importlib.util.module_from_spec(spec)
sys.modules["build_codex"] = build_codex
spec.loader.exec_module(build_codex)

from ra2agent.rules import ARMOR_TYPES  # noqa: E402


class TestFormatDamage(unittest.TestCase):
    def test_groups_equal_values(self):
        # 11 个位置里同值的并成一档，省一半长度
        values = [15, 15, 12, 12, 7, 7, 7, 7, 7, 7, 15]
        text = build_codex.format_damage(values)
        self.assertEqual(text.split()[0], f"{ARMOR_TYPES[0]},{ARMOR_TYPES[1]},{ARMOR_TYPES[10]}=15")

    def test_uses_equals_so_armor_names_stay_unambiguous(self):
        # `special_1` 结尾是数字，`special_115` 分不清是打 15 还是别的
        values = [1] * (len(ARMOR_TYPES) - 1) + [15]
        text = build_codex.format_damage(values)
        self.assertIn("special_2=15", text)
        self.assertIn("special_1=1", text)

    def test_all_equal_collapses_to_one_group(self):
        values = [7] * len(ARMOR_TYPES)
        self.assertEqual(build_codex.format_damage(values),
                         ",".join(ARMOR_TYPES) + "=7")

    def test_covers_every_armor(self):
        text = build_codex.format_damage([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
        for armor in ARMOR_TYPES:
            self.assertIn(armor, text)


class TestLoadNotes(unittest.TestCase):
    def test_missing_file_is_empty(self):
        self.assertEqual(build_codex.load_notes("nope.md"), {})

    def test_reads_id_and_text(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tech_buildings.md").write_text(
                "# 标题\n<!-- 注释 -->\nCAOILD 占领后持续给钱\n\nCAMACH 修理载具\n",
                encoding="utf-8")
            original, build_codex.NOTES = build_codex.NOTES, root
            try:
                notes = build_codex.load_notes("tech_buildings.md")
            finally:
                build_codex.NOTES = original
        self.assertEqual(notes, {"CAOILD": "占领后持续给钱", "CAMACH": "修理载具"})


if __name__ == "__main__":
    unittest.main()
