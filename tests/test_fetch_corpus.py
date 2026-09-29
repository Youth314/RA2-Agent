"""`tools/fetch_corpus.py` 的测试。

只测纯函数。网络那部分靠 `--max` 冒烟，不进单元测试——它依赖外部站点。
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_corpus as fc  # noqa: E402


class TestWantCategory(unittest.TestCase):
    def test_keeps_content_categories(self):
        for name in ("Red Alert 2 Infantry", "Red Alert 2 Tactics",
                     "Red Alert 2 Buildings", "Yuri's Revenge Yuri arsenal",
                     "Red Alert 2 cut content"):
            with self.subTest(name=name):
                self.assertTrue(fc.want_category(name))

    def test_rejects_media_categories(self):
        # 这些分类底下只有图片，对决策没有价值
        for name in ("Red Alert 2 images", "Red Alert 2 Allied cameos",
                     "Yuri's Revenge concept art", "Red Alert 2 unit images",
                     "Red Alert 2 promotional artwork", "Yuri's Revenge icons"):
            with self.subTest(name=name):
                self.assertFalse(fc.want_category(name))

    def test_rejects_other_games(self):
        for name in ("Tiberian Sun", "Generals", "Red Alert 3 units", "Missions"):
            with self.subTest(name=name):
                self.assertFalse(fc.want_category(name))

    def test_arsenal_is_not_mistaken_for_art(self):
        # 曾经的写法用子串 "art" 过滤，会误伤 arsenal/Headquarters/Heartland
        for name in ("Red Alert 2 Arsenal", "Red Alert 2 Soviet arsenal",
                     "Yuri's Revenge Allied arsenal"):
            with self.subTest(name=name):
                self.assertTrue(fc.want_category(name))


class TestPageRecord(unittest.TestCase):
    def test_builds_a_record(self):
        page = {"pageid": 7, "title": "Grizzly Battle Tank",
                "revisions": [{"slots": {"main": {"content": "正文"}}}]}
        record = fc.page_record(page, "cnc.fandom.com")
        self.assertEqual(record["pageid"], 7)
        self.assertEqual(record["title"], "Grizzly Battle Tank")
        self.assertEqual(record["content"], "正文")
        self.assertIn("Grizzly_Battle_Tank", record["url"])

    def test_keeps_non_latin_titles_readable(self):
        page = {"pageid": 8, "title": "红警 2",
                "revisions": [{"slots": {"main": {"content": "正文"}}}]}
        self.assertIn("%E7%BA%A2%E8%AD%A6", fc.page_record(page, "w")["url"])

    def test_skips_pages_without_content(self):
        pages = ({"pageid": 1, "title": "x"},
                 {"pageid": 1, "title": "x", "revisions": []},
                 {"pageid": 1, "title": "x",
                  "revisions": [{"slots": {"main": {"content": ""}}}]},
                 {"pageid": 1, "title": "x", "revisions": [{}]})
        for page in pages:
            with self.subTest(page=page):
                self.assertIsNone(fc.page_record(page, "w"))


class TestJsonl(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pages.jsonl"
            fc.append_records(path, [{"pageid": 1, "title": "a", "content": "x"},
                                     {"pageid": 2, "title": "b", "content": "y"}])
            self.assertEqual(fc.load_done(path), {1, 2})

    def test_appending_does_not_rewrite(self):
        # 断点续跑靠追加：重跑一次不会丢掉已经取到的
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pages.jsonl"
            fc.append_records(path, [{"pageid": 1, "title": "a", "content": "x"}])
            fc.append_records(path, [{"pageid": 2, "title": "b", "content": "y"}])
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)

    def test_empty_records_touch_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pages.jsonl"
            fc.append_records(path, [])
            self.assertFalse(path.exists())

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(fc.load_done(Path(tmp) / "nope.jsonl"), set())

    def test_malformed_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pages.jsonl"
            path.write_text('{"pageid": 3}\n不是 json\n\n', encoding="utf-8")
            self.assertEqual(fc.load_done(path), {3})


if __name__ == "__main__":
    unittest.main()
