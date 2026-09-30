"""可造目录：前提、可达性、阵营分离。

纯数据与纯查询，不碰游戏。用合成条目而不是真读 `corpus/derived/rules.json`——
真文件有五百多条，测试要的是判据本身。
"""
import unittest

from ra2agent.catalogue import Catalogue, Entry


def entry(identifier, *, name=None, kind="building", cost=100, tech=1,
          prerequisite=(), owners=("Alliance",), stolen_tech="", water_bound=False):
    return Entry(id=identifier, name=name or identifier, kind=kind, cost=cost,
                 tech_level=tech, prerequisite=tuple(prerequisite),
                 owners=tuple(owners), stolen_tech=stolen_tech,
                 water_bound=water_bound)


def chain():
    """一条盟军链：建造厂 → 电厂 → 兵营/矿厂 → 重工 → 坦克。"""
    return Catalogue([
        entry("GACNST", name="Construction Yard", cost=2500),
        entry("GAPOWR", name="Allied Power Plant", cost=800,
              prerequisite=("GACNST",)),
        entry("GAPILE", name="Allied Barracks", cost=500, tech=2,
              prerequisite=("POWER", "GACNST")),
        entry("GAREFN", name="Allied Ore Refinery", cost=2000,
              prerequisite=("POWER", "GACNST")),
        entry("GAWEAP", name="Allied War Factory", cost=2000, tech=2,
              prerequisite=("PROC", "GAPILE", "GACNST")),
        entry("E1", name="GI", kind="infantry", cost=200,
              prerequisite=("GAPILE",)),
        entry("MTNK", name="Grizzly Battle Tank", kind="vehicle", cost=700, tech=2,
              prerequisite=("GAWEAP",)),
        # 对方的根：`NACNST` 不在盟军的 owners 里，故盟军推不到它
        entry("NACNST", name="Soviet Construction Yard", cost=2500,
              owners=("Russians",)),
        entry("NAPOWR", name="Soviet Power Plant", cost=800,
              prerequisite=("NACNST",), owners=("Russians",)),
    ])


class TestEntry(unittest.TestCase):
    def test_alias_means_any_of_them(self):
        gapowr = chain().by_id["GAPOWR"]
        self.assertEqual(gapowr.missing(frozenset()), ("GACNST",))
        self.assertEqual(gapowr.missing(frozenset({"GACNST"})), ())

    def test_alias_power_is_satisfied_by_a_power_plant(self):
        garefn = chain().by_id["GAREFN"]
        owned = frozenset({"GACNST"})
        self.assertEqual(garefn.missing(owned), ("POWER",))
        self.assertEqual(garefn.missing(owned | {"GAPOWR"}), ())

    def test_unknown_token_matches_by_registration_name(self):
        gaweap = chain().by_id["GAWEAP"]
        owned = frozenset({"GACNST", "GAPOWR", "GAREFN", "GAPILE"})
        self.assertEqual(gaweap.missing(owned), ())     # PROC 由 GAREFN 满足

    def test_props_are_not_buildable(self):
        """民用道具（造价 0、TechLevel=-1）不该进清单。"""
        self.assertFalse(entry("AMMOCRAT", cost=0, tech=-1).buildable)
        self.assertTrue(entry("GAPOWR", cost=800, tech=1).buildable)

    def test_stolen_tech_is_a_gate_of_its_own(self):
        """`RequiresStolen*Tech` 不在 `Prerequisite` 里，引擎却会卡。

        实测：超时空突击队只写 `Prerequisite=BARRACKS`，本地说「现在就能造」，
        下单后被 `unbuildable` 拒——真门是「偷到盟军科技」。
        """
        commando = entry("CCOMAND", kind="infantry", prerequisite=("BARRACKS",),
                         stolen_tech="allied")
        self.assertIn("窃取盟军科技", commando.missing(frozenset({"GAPILE"})))
        self.assertEqual(
            commando.missing(frozenset({"GAPILE"}), stolen=frozenset({"窃取盟军科技"})),
            ())

    def test_water_bound_is_a_gate_when_we_know_there_is_no_water(self):
        """临水建筑：**判不了就别说**（`None`），确知没水才算缺。"""
        shipyard = entry("GAYARD", water_bound=True)
        self.assertEqual(shipyard.missing(frozenset(), water_near=False),
                         ("临水（基地附近要有水面）",))
        self.assertEqual(shipyard.missing(frozenset(), water_near=None), ())

    def test_stolen_tech_entries_still_show_up_in_the_list(self):
        """偷没偷到是当前状态，不该让整条分支从清单里消失——否则模型学不到它存在。"""
        catalogue = Catalogue([
            entry("GACNST"),
            entry("GAPILE", prerequisite=("POWER", "GACNST")),
            entry("GAPOWR", prerequisite=("GACNST",)),
            entry("CCOMAND", kind="infantry", prerequisite=("GAPILE",),
                  stolen_tech="allied"),
        ])
        listed = {e.id: m for e, m in catalogue.candidates(
            {"GACNST", "GAPOWR", "GAPILE"}, faction="Alliance", buildings=False)}
        self.assertIn("CCOMAND", listed)
        self.assertIn("窃取盟军科技", listed["CCOMAND"])


class TestCatalogue(unittest.TestCase):
    def test_finds_by_id_and_by_display_name(self):
        catalogue = chain()
        self.assertEqual(catalogue.entry("GAPOWR").name, "Allied Power Plant")
        self.assertEqual(catalogue.entry("Allied Power Plant").id, "GAPOWR")

    def test_reachable_is_eventual_not_immediate(self):
        """可达 = 顺着前提链**最终造得到**，不是「现在就能造」。

        只有建造厂时电厂先可达，电厂一到手兵营也就可达了——故整条盟军链都在。
        """
        catalogue = chain()
        known = catalogue.reachable({"GACNST"}, faction="Alliance")
        for identifier in ("GAPOWR", "GAPILE", "GAREFN", "GAWEAP", "E1", "MTNK"):
            self.assertIn(identifier, known)

    def test_other_side_stays_unreachable(self):
        """阵营分离靠前提链的根：盟军推不出 `NACNST`。

        建筑的 `Owner` 把十个国家都列了，光看它分不出盟苏；`NACNST` 的 owners
        只有苏军四国，故盟军这边根本走不到它，连带 `NAPOWR` 也不可达。
        """
        catalogue = chain()
        known = catalogue.reachable({"GACNST", "GAPOWR", "GAREFN", "GAPILE",
                                     "GAWEAP"}, faction="Alliance")
        self.assertNotIn("NACNST", known)
        self.assertNotIn("NAPOWR", known)
        listed = [e.id for e, _ in catalogue.candidates(
            {"GACNST"}, faction="Alliance", buildings=True)]
        self.assertNotIn("NAPOWR", listed)

    def test_candidates_put_what_you_can_build_first(self):
        catalogue = chain()
        found = catalogue.candidates({"GACNST"}, faction="Alliance", buildings=True)
        self.assertEqual(found[0][0].id, "GAPOWR")
        self.assertEqual(found[0][1], ())               # 现在就能造

    def test_candidates_rank_by_how_much_is_missing(self):
        """「缺得最少」的排前面；够得着的远分支也看得到，但排在后面。"""
        catalogue = chain()
        found = catalogue.candidates({"GACNST"}, faction="Alliance", buildings=True)
        listed = {entry.id: missing for entry, missing in found}
        order = list(listed)
        self.assertEqual(order[0], "GAPOWR")
        self.assertEqual(listed["GAWEAP"], ("PROC", "GAPILE"))   # 建造厂已有
        self.assertGreater(order.index("GAWEAP"), order.index("GAPOWR"))

    def test_candidates_mark_what_is_still_missing(self):
        catalogue = chain()
        found = catalogue.candidates({"GACNST"}, faction="Alliance", buildings=True)
        listed = {entry.id: missing for entry, missing in found}
        self.assertEqual(listed["GAPILE"], ("POWER",))   # 还差一座电厂
        self.assertEqual(listed["GAPOWR"], ())           # 现在就能造

    def test_ready_entries_put_the_big_ticket_first(self):
        """能造的按贵在前：清单有上限，重工不该被围墙挤掉。

        实测：矿厂好后重工已可造，却因按造价升序排在第 9 位被上限截掉，模型在
        清单里根本找不到它——只能自己猜着下单，而清单本来就是为了省掉这个猜。
        """
        catalogue = chain()
        found = catalogue.candidates({"GACNST", "GAPOWR", "GAREFN", "GAPILE"},
                                     faction="Alliance", buildings=True, limit=3)
        ids = [entry.id for entry, _ in found]
        self.assertEqual(ids[0], "GAWEAP")
        self.assertIn("GAREFN", ids)

    def test_not_ready_entries_put_the_next_step_first(self):
        """还缺前提的按便宜在前：下一步该补什么，要排在够不着的超武前面。"""
        catalogue = chain()
        found = catalogue.candidates({"GACNST"}, faction="Alliance", buildings=True)
        not_ready = [entry.id for entry, missing in found if missing]
        self.assertEqual(not_ready[0], "GAPILE")     # 500 块、只差一座电厂

    def test_missing_catalogue_is_not_an_error(self):
        self.assertEqual(len(Catalogue.load("/nonexistent/rules.json")), 0)


if __name__ == "__main__":
    unittest.main()
