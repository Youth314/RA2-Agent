"""`payloads` 的指针编码。

起因是一个实测事故：`status` 只要遇到「建筑完工待放置」就必抛

    TypeError: int() argument must be a string, a bytes-like object or a real number,
    not 'House'

根因是 `payloads._pointer_of` 只认 `GameObject`/`ObjectType`，而 `PlaceQuery` 要的
`house_class` 来自 `state.player_house()`——那是个 `House` 数据类实例。少认一种就
落到 `int(obj)`，而调用点在读局势的路径上，一次异常就让整个 `status` 不可用。
故这里钉住「凡带 `pointer` 的都取得出指针」。
"""
import unittest
from types import SimpleNamespace

from ra2agent.payloads import _pointer_of, place_query
from ra2agent.state import House


def make_house(pointer=123456):
    """一个够用的 `House`。"""
    return House(pointer=pointer, array_index=0, name="Alpha",
                 faction="Americans", money=100, current_player=True,
                 is_human_player=True, defeated=False, is_winner=False,
                 is_loser=False)


class TestPointerOf(unittest.TestCase):
    def test_bare_pointer_passes_through(self):
        self.assertEqual(_pointer_of(7), 7)

    def test_house_pointer(self):
        """`House` 有 `pointer` 字段，取得到——这条以前是抛 `TypeError` 的。"""
        self.assertEqual(_pointer_of(make_house(4242)), 4242)

    def test_anything_with_a_pointer_field(self):
        self.assertEqual(_pointer_of(SimpleNamespace(pointer=99)), 99)


class TestPlaceQuery(unittest.TestCase):
    def test_house_object_encodes(self):
        """整条 `PlaceQuery` 编码路径拿 `House` 对象也不该炸。"""
        entry = SimpleNamespace(pointer=555)
        encoded = place_query(entry, make_house(4242), [])
        self.assertIsInstance(encoded, bytes)
        self.assertTrue(encoded)


if __name__ == "__main__":
    unittest.main()
