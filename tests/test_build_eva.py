"""副官对照表生成器的测试。

全是离线假件：一份手写的迷你 `evamd.ini` 加一份手写标注，不碰真文件。
"""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))

import build_eva  # noqa: E402

SAMPLE = """[DialogList]
0=EVA_UnitLost

[EVA_UnitLost]
Text=Unit lost.
Priority=IMPORTANT
Type=QUEUE

[EVA_NuclearSiloDetected]
Text=Warning:  Nuclear Silo detected.
Priority=IMPORTANT

[EVA_PsychicRevealReady]  ; This event was added too late.
Text=
Russian=spsyread

[Unit_Eva_Kirov]
Text=
Russian=cevau08

[Unit_Sofia_Kirov]
Text=
Russian=csofu08
"""


class TestParseIni(unittest.TestCase):
    def test_reads_sections_and_keys(self):
        sections = build_eva.parse_ini(SAMPLE)
        self.assertEqual(sections["EVA_UnitLost"]["Text"], "Unit lost.")
        self.assertEqual(sections["EVA_UnitLost"]["Priority"], "IMPORTANT")

    def test_header_may_carry_a_comment(self):
        # 原文件里这一行的节头后面跟着 `; This event was added too late.`
        self.assertIn("EVA_PsychicRevealReady", build_eva.parse_ini(SAMPLE))

    def test_comments_are_stripped_from_values(self):
        sections = build_eva.parse_ini("[A]\nText=hi  ; note\n")
        self.assertEqual(sections["A"]["Text"], "hi")

    def test_missing_file_section_is_not_invented(self):
        self.assertNotIn("EVA_NotThere", build_eva.parse_ini(SAMPLE))


class TestCollect(unittest.TestCase):
    def collect(self, annotations=None):
        return build_eva.collect(build_eva.parse_ini(SAMPLE), annotations or {})

    def test_events_and_reports_are_split(self):
        events, reports = self.collect()
        # 排序按优先级，同为 IMPORTANT 时按名字
        self.assertEqual([e["name"] for e in events],
                         ["EVA_NuclearSiloDetected", "EVA_UnitLost", "EVA_PsychicRevealReady"])
        self.assertEqual(len(reports), 1, "两套副官合并成一条")

    def test_queue_flag_comes_from_type(self):
        events, _ = self.collect()
        by_name = {e["name"]: e for e in events}
        self.assertTrue(by_name["EVA_UnitLost"]["queue"])
        self.assertFalse(by_name["EVA_NuclearSiloDetected"]["queue"])

    def test_the_two_announcers_merge_into_one_row(self):
        # 两套副官只有语音不同
        _, reports = self.collect()
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["unit"], "Kirov")
        self.assertEqual(reports[0]["voices"], ["eva", "sofia"])

    def test_unit_reports_get_the_class_default(self):
        # 引擎无条件全图播报出厂，我们按迷雾观测，故合成不了
        _, reports = self.collect()
        self.assertEqual(reports[0]["visibility"], "全图")
        self.assertEqual(reports[0]["synthesizable"], "不可")

    def test_annotation_overrides_the_default(self):
        _, reports = self.collect({"Unit_Eva_Kirov": {"visibility": "存疑"}})
        self.assertEqual(reports[0]["visibility"], "存疑")

    def test_events_sort_by_priority(self):
        # 没写 Priority 的排在最后
        events, _ = self.collect()
        rank = lambda p: (build_eva.PRIORITY_ORDER.index(p)  # noqa: E731
                          if p in build_eva.PRIORITY_ORDER else len(build_eva.PRIORITY_ORDER))
        order = [rank(e["priority"]) for e in events]
        self.assertEqual(order, sorted(order))


class TestAnnotations(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "eva_annotations.md"
            path.write_text(text, encoding="utf-8")
            original = build_eva.NOTES
            build_eva.NOTES = path
            try:
                return build_eva.load_annotations()
            finally:
                build_eva.NOTES = original

    def test_reads_every_field(self):
        got = self.load("EVA_UnitLost | 损失与受袭 | 单位阵亡 | 己方 | 可\n")
        self.assertEqual(got["EVA_UnitLost"]["category"], "损失与受袭")
        self.assertEqual(got["EVA_UnitLost"]["chinese"], "单位阵亡")
        self.assertEqual(got["EVA_UnitLost"]["visibility"], "己方")
        self.assertEqual(got["EVA_UnitLost"]["synthesizable"], "可")

    def test_missing_trailing_fields_are_empty(self):
        self.assertEqual(self.load("EVA_UnitLost | 损失与受袭\n")["EVA_UnitLost"]["chinese"], "")

    def test_prose_is_not_an_annotation(self):
        # 说明文字里的竖线不该被当成标注，否则闸门会报一堆认不出的名字
        got = self.load("# 标题\n`codex/eva.md` 的「可见性」与「可合成」两列\n可用：`可` / `不可`\n")
        self.assertEqual(got, {})

    def test_fenced_code_is_skipped(self):
        got = self.load("```\n事件名 | 可见性 | 可合成 | 依据\n```\n")
        self.assertEqual(got, {})


class TestUnknownNames(unittest.TestCase):
    def test_render_lists_names_absent_from_the_ini(self):
        events, reports = build_eva.collect(build_eva.parse_ini(SAMPLE), {})
        text = build_eva.render(events, reports, {"EVA_Typo": {"visibility": "己方"}})
        self.assertIn("EVA_Typo", text)
        self.assertIn("认不出的名字", text)


if __name__ == "__main__":
    unittest.main()
