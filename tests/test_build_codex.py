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


class TestGlossary(unittest.TestCase):
    """俗名表的解析。用临时文件替换 NOTES，不依赖仓库里的具体内容。"""

    def _load(self, text):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "glossary.md").write_text(text, encoding="utf-8")
            original, build_codex.NOTES = build_codex.NOTES, root
            try:
                return build_codex.load_glossary()
            finally:
                build_codex.NOTES = original

    def test_reads_entities_with_nicknames(self):
        entities, _ = self._load("## 载具\n\nMTNK 灰熊坦克：小坦克、瘦坦克、报纸壳壳\n")
        self.assertEqual(entities, [{"id": "MTNK", "name": "灰熊坦克",
                                     "nicknames": ["小坦克", "瘦坦克", "报纸壳壳"],
                                     "unconfirmed": False}])

    def test_accepts_two_letter_ids(self):
        # E1 / V3 只有两个字符，量词写成 {2,} 会把它们漏掉
        entities, _ = self._load("## 兵种\n\nE1 美国大兵：机枪兵\n\nV3 V3 导弹车：火箭\n")
        self.assertEqual([e["id"] for e in entities], ["E1", "V3"])
        self.assertEqual(entities[1]["name"], "V3 导弹车")

    def test_missing_nickname_reads_as_empty(self):
        entities, _ = self._load("## 载具\n\nZEP 基洛夫飞艇：无\n")
        self.assertEqual(entities[0]["nicknames"], [])

    def test_marks_unconfirmed(self):
        entities, _ = self._load("## 舰船\n\nSAPC 装甲运输船：重船 ❓\n")
        self.assertTrue(entities[0]["unconfirmed"])
        self.assertEqual(entities[0]["nicknames"], ["重船"])

    def test_header_prose_is_not_a_term(self):
        # 文件头有 `来源两份：…` 这种行，不能被当成黑话
        _, terms = self._load("来源两份：\n\n一行一条：`注册名 中文名：俗名`\n\n## 战术黑话\n\n吃牛肉：打矿车\n")
        self.assertEqual(terms, [{"term": "吃牛肉", "meaning": "打矿车"}])

    def test_entity_lines_are_not_terms(self):
        _, terms = self._load("## 兵种\n\nE2 动员兵：炮灰兵\n\n## 战术黑话\n\nTR：塔攻\n")
        self.assertEqual([t["term"] for t in terms], ["TR"])


class TestBuildGlossary(unittest.TestCase):
    def test_renders_entities_and_terms(self):
        text = build_codex.build_glossary(
            [{"id": "MTNK", "name": "灰熊坦克", "nicknames": ["小坦克"],
              "unconfirmed": False}],
            [{"term": "吃牛肉", "meaning": "打矿车"}])
        self.assertIn("**MTNK** 灰熊坦克：小坦克", text)
        self.assertIn("## 战术黑话", text)
        self.assertIn("**吃牛肉**：打矿车", text)

    def test_marks_unconfirmed_and_empty(self):
        text = build_codex.build_glossary(
            [{"id": "SHAD", "name": "夜莺直升机", "nicknames": [],
              "unconfirmed": True}], [])
        self.assertIn("夜莺直升机 ❓：（无）", text)


class TestNames(unittest.TestCase):
    def _load(self, derived, notes):
        import json as _json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "corpus" / "derived").mkdir(parents=True)
            (root / "corpus" / "derived" / "names.json").write_text(
                _json.dumps({"source": "x", "names": derived}), encoding="utf-8")
            (root / "corpus" / "notes").mkdir(parents=True)
            if notes is not None:
                (root / "corpus" / "notes" / "names.md").write_text(notes, encoding="utf-8")
            original_repo, original_notes = build_codex.REPO, build_codex.NOTES
            build_codex.REPO, build_codex.NOTES = root, root / "corpus" / "notes"
            try:
                return build_codex.load_names()
            finally:
                build_codex.REPO, build_codex.NOTES = original_repo, original_notes

    def test_derived_names_are_used(self):
        self.assertEqual(self._load({"MTNK": "灰熊坦克"}, None), {"MTNK": "灰熊坦克"})

    def test_hand_written_names_win(self):
        names = self._load({"HIND": "印度"}, "HIND 雌鹿运输直升机\n")
        self.assertEqual(names["HIND"], "雌鹿运输直升机")

    def test_unconfirmed_marker_is_stripped(self):
        self.assertEqual(self._load({}, "YDOG 尤里警犬 ❓\n"), {"YDOG": "尤里警犬"})

    def test_missing_files_are_tolerated(self):
        self.assertEqual(self._load({}, None), {})


class TestUnused(unittest.TestCase):
    def test_zzz_prefix_marks_unused(self):
        holder = type("H", (), {"name": "ZZZ Not Used", "id": "UTNK"})()
        self.assertTrue(build_codex.is_unused(holder))

    def test_engine_placeholders_mark_unused(self):
        for name in ("Placeholder", "DeathDummy"):
            holder = type("H", (), {"name": name, "id": "X"})()
            with self.subTest(name=name):
                self.assertTrue(build_codex.is_unused(holder))

    def test_real_units_are_not_unused(self):
        holder = type("H", (), {"name": "Grizzly Battle Tank", "id": "MTNK"})()
        self.assertFalse(build_codex.is_unused(holder))


class TestWithName(unittest.TestCase):
    def test_appends_chinese(self):
        holder = type("H", (), {"name": "Grizzly Battle Tank", "id": "MTNK"})()
        self.assertEqual(build_codex.with_name(holder, {"MTNK": "灰熊坦克"}),
                         "Grizzly Battle Tank（灰熊坦克）")

    def test_falls_back_to_english(self):
        holder = type("H", (), {"name": "Something", "id": "NOPE"})()
        self.assertEqual(build_codex.with_name(holder, {}), "Something")


class TestFaction(unittest.TestCase):
    def _holder(self, **kwargs):
        base = {"id": "X", "owners": (), "prerequisite": ()}
        base.update(kwargs)
        return type("H", (), base)()

    SIDES = {"Americans": "GDI", "French": "GDI", "Russians": "Nod", "YuriCountry": "ThirdSide"}

    def test_unit_side_from_owners(self):
        self.assertEqual(build_codex.unit_side(self._holder(owners=("Americans", "French")), self.SIDES), "GDI")
        self.assertEqual(build_codex.unit_side(self._holder(owners=("Russians",)), self.SIDES), "Nod")
        self.assertEqual(build_codex.unit_side(self._holder(owners=("YuriCountry",)), self.SIDES), "ThirdSide")

    def test_cross_faction_unit_has_no_side(self):
        self.assertIsNone(build_codex.unit_side(self._holder(owners=("Americans", "Russians")), self.SIDES))
        self.assertIsNone(build_codex.unit_side(self._holder(owners=()), self.SIDES))

    def test_construction_yard_identifies_the_side(self):
        for yard, side in build_codex.CONSTRUCTION_YARDS.items():
            with self.subTest(yard=yard):
                self.assertEqual(build_codex.building_side(self._holder(id=yard), {}), side)

    def test_building_side_walks_prerequisites(self):
        # 建筑的 Owner 全都列了所有国家，只能顺着前提链追到建造厂
        index = {"GACNST": self._holder(id="GACNST"),
                 "GAPILE": self._holder(id="GAPILE", prerequisite=("GACNST",))}
        lab = self._holder(id="GATECH", prerequisite=("GAWEAP", "RADAR", "GACNST"))
        index["GATECH"] = lab
        self.assertEqual(build_codex.building_side(lab, index), "GDI")

    def test_generic_prerequisites_are_skipped(self):
        # RADAR / PROC 这类通用前提不在表里，跳过即可
        index = {"NACNST": self._holder(id="NACNST")}
        lab = self._holder(id="NATECH", prerequisite=("NAWEAP", "RADAR", "NACNST"))
        index["NATECH"] = lab
        self.assertEqual(build_codex.building_side(lab, index), "Nod")

    def test_cycles_do_not_hang(self):
        index = {}
        a = self._holder(id="A", prerequisite=("B",))
        b = self._holder(id="B", prerequisite=("A",))
        index.update({"A": a, "B": b})
        self.assertIsNone(build_codex.building_side(a, index))
