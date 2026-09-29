"""`ra2agent.rules` 的测试。

用一小段合成 INI，不依赖 `corpus/raw/`（那份不入库）。
"""
import unittest

from ra2agent.rules import (ARMOR_TYPES, Rules, Warhead, as_bool, as_int,
                            as_list, load_sections, parse_rules, parse_verses,
                            strip_comment)

SAMPLE = """
; 一段合成 rulesmd.ini，形状照抄真实文件
[InfantryTypes]
0=E1
1=GGI

[VehicleTypes]
0=MTNK

[AircraftTypes]

[BuildingTypes]
0=GAPOWR
1=CAOILD
2=GAPILL

[ArmorTypes]

[E1]
Name=G.I.
Cost=200
Strength=125
Armor=none
Speed=4
Sight=5
TechLevel=1
Prerequisite=GAPILE
Owner=Americans,British
Primary=M60
Secondary=RedEye2

[GGI]
Name=Guardian GI
Cost=250
Strength=150
Armor=flak
Primary=M60

[MTNK]
Name=Grizzly Battle Tank
Cost=700
Strength=300
Armor=heavy
Speed=7
Sight=8
TechLevel=2
Prerequisite=GAWEAP
Owner=Americans,Alliance
Primary=105mm

[GAPOWR]
Name=Allied Power Plant
Cost=800
Strength=750
Armor=wood
Power=100
TechLevel=1
Prerequisite=GACNST
Owner=Americans
Capturable=true
Primary=AGGun

[CAOILD]
Name=Tech Oil Derrick
TechLevel=-1
Capturable=yes
CanBeOccupied=no

[GAPILL]
Name=Pillbox
Cost=400
Strength=400
Armor=steel
CanBeOccupied=yes
MaxNumberOccupants=5
Foundation=1x1

[M60]
Damage=15
ROF=20
Range=4
Warhead=SA

[105mm]
Damage=65
ROF=60
Range=5
Warhead=AP

[AGGun]
Damage=25
ROF=30
Range=6
Warhead=SA

[SA]
Verses=100%,80%,70%,50%,25%,25%,75%,50%,25%,100%,100%

[AP]
Verses=25%,25%,15%,75%,100%,100%,65%,45%,60%,60%,100%
"""


class TestTextHelpers(unittest.TestCase):
    def test_strip_comment(self):
        self.assertEqual(strip_comment("Cost=700  ; 造价"), "Cost=700")
        self.assertEqual(strip_comment("   ; 整行注释"), "")

    def test_as_bool_accepts_both_spellings(self):
        # 实测里同一个意思写成 yes / true / 缺失 三种
        for text in ("yes", "YES", "true", "True", "1", " yes "):
            with self.subTest(text=text):
                self.assertTrue(as_bool(text))
        for text in ("no", "false", "0", "", None):
            with self.subTest(text=text):
                self.assertFalse(as_bool(text))

    def test_as_int_falls_back(self):
        self.assertEqual(as_int("700"), 700)
        self.assertEqual(as_int("abc", -1), -1)
        self.assertEqual(as_int(None, 7), 7)

    def test_as_list(self):
        self.assertEqual(as_list("A, B ,C"), ("A", "B", "C"))
        self.assertEqual(as_list(""), ())
        self.assertEqual(as_list(None), ())

    def test_parse_verses_strips_percent(self):
        self.assertEqual(parse_verses("25%,100%"), (25, 100))
        self.assertEqual(parse_verses(""), ())


class TestLoadSections(unittest.TestCase):
    def test_reads_sections_and_keys(self):
        sections = load_sections(SAMPLE)
        self.assertEqual(sections["E1"]["Name"], "G.I.")
        self.assertEqual(sections["MTNK"]["Cost"], "700")

    def test_keeps_empty_sections(self):
        # [AircraftTypes] 是空的，但后面要按它取清单，不能丢
        self.assertIn("AircraftTypes", load_sections(SAMPLE))
        self.assertEqual(load_sections(SAMPLE)["AircraftTypes"], {})

    def test_ignores_lines_before_any_section(self):
        self.assertEqual(load_sections("Cost=1\n[E1]\nCost=2\n")["E1"], {"Cost": "2"})


class TestWarhead(unittest.TestCase):
    def test_multiplier_follows_the_armor_order(self):
        warhead = Warhead(id="AP", verses=(25, 100))
        self.assertEqual(warhead.multiplier("none"), 0.25)
        self.assertEqual(warhead.multiplier("flak"), 1.0)

    def test_armor_order_matches_modenc(self):
        # 出处：ModEnc 的 Verses 页。顺序错了整张克制表就全错
        self.assertEqual(ARMOR_TYPES[0], "none")
        self.assertEqual(ARMOR_TYPES[3], "light")
        self.assertEqual(ARMOR_TYPES[5], "heavy")
        self.assertEqual(len(ARMOR_TYPES), 11)

    def test_unknown_or_missing_armor_is_full_damage(self):
        warhead = Warhead(id="X", verses=())
        self.assertEqual(warhead.multiplier("nope"), 1.0)
        self.assertEqual(warhead.multiplier("heavy"), 1.0)
        self.assertEqual(warhead.multiplier(None), 1.0)


class TestParseRules(unittest.TestCase):
    def setUp(self):
        self.rules = parse_rules(SAMPLE)

    def test_units_carry_their_kind(self):
        kinds = {u.id: u.kind for u in self.rules.units}
        self.assertEqual(kinds, {"E1": "infantry", "GGI": "infantry",
                                 "MTNK": "vehicle"})

    def test_unit_fields(self):
        tank = self.rules.unit("MTNK")
        self.assertEqual(tank.name, "Grizzly Battle Tank")
        self.assertEqual((tank.cost, tank.strength, tank.armor), (700, 300, "heavy"))
        self.assertEqual(tank.prerequisite, ("GAWEAP",))
        self.assertEqual(tank.owners, ("Americans", "Alliance"))

    def test_missing_tech_level_reads_as_minus_one(self):
        self.assertEqual(self.rules.unit("MTNK").tech_level, 2)
        self.assertEqual(self.rules.building("CAOILD").tech_level, -1)

    def test_buildings_carry_occupancy(self):
        pillbox = self.rules.building("GAPILL")
        self.assertTrue(pillbox.can_be_occupied)
        self.assertEqual(pillbox.max_occupants, 5)
        self.assertEqual(pillbox.foundation, "1x1")
        self.assertFalse(pillbox.capturable)

    def test_neutral_tech_building_is_capturable(self):
        derrick = self.rules.building("CAOILD")
        self.assertTrue(derrick.capturable)
        self.assertEqual(derrick.cost, 0)

    def test_building_weapons_are_collected_too(self):
        # 光棱塔、防空炮的伤害也要算，故建筑上的武器同样要收
        self.assertIn("AGGun", self.rules.weapons)

    def test_only_reachable_weapons_are_kept(self):
        # 没有 [Weapons] 清单节，只能顺着引用走
        self.assertEqual(set(self.rules.weapons), {"M60", "105mm", "AGGun"})
        self.assertNotIn("NeverUsed", self.rules.weapons)

    def test_warheads_come_from_weapons(self):
        self.assertEqual(set(self.rules.warheads), {"SA", "AP"})

    def test_damage_per_shot(self):
        tank = self.rules.unit("MTNK")
        self.assertEqual(self.rules.damage_per_shot(tank, self.rules.unit("MTNK")), 65.0)
        self.assertAlmostEqual(self.rules.damage_per_shot(tank, self.rules.unit("E1")), 16.25)

    def test_damage_per_shot_uses_the_defenders_armor(self):
        tank = self.rules.unit("MTNK")
        rifleman = self.rules.unit("E1")
        pillbox = self.rules.building("GAPILL")
        self.assertAlmostEqual(self.rules.damage_per_shot(tank, rifleman), 16.25)   # none
        self.assertAlmostEqual(self.rules.damage_per_shot(tank, pillbox), 29.25)   # steel

    def test_damage_per_shot_without_a_weapon_is_none(self):
        derrick = self.rules.building("CAOILD")
        self.assertIsNone(self.rules.damage_per_shot(derrick, derrick))

    def test_empty_rules_is_usable(self):
        empty = Rules()
        self.assertEqual((empty.units, empty.buildings), ((), ()))
        self.assertIsNone(empty.unit("MTNK"))


if __name__ == "__main__":
    unittest.main()
