# -*- coding: utf-8 -*-
"""拟人化输入模块的回归测试（零浏览器：用假 page/mouse 记录调用序列）。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import human_click as hc


class _FakeMouse:
    def __init__(self):
        self.moves = []
        self.downs = 0
        self.ups = 0

    def move(self, x, y):
        self.moves.append((round(x, 2), round(y, 2)))

    def down(self):
        self.downs += 1

    def up(self):
        self.ups += 1


class _FakeBox:
    def __init__(self, box):
        self._box = box

    def bounding_box(self):
        return self._box

    def scroll_into_view_if_needed(self, timeout=None):
        return None

    def evaluate(self, js):
        return None

    def type(self, ch, delay=0):
        return None


class _FakePage:
    def __init__(self, box=None):
        self.mouse = _FakeMouse()
        self._box = box or {"x": 100, "y": 200, "width": 60, "height": 24}


class CurveTests(unittest.TestCase):
    def test_endpoints_exact(self):
        pts = hc.curve_points((0, 0), (5, 10), (10, 0), steps=8)
        self.assertEqual(len(pts), 9)
        self.assertEqual(pts[0], (0, 0))
        self.assertEqual(pts[-1], (10, 0))

    def test_path_is_not_straight_line(self):
        pts = hc.curve_points((0, 0), (5, 10), (10, 0), steps=10)
        mid = pts[5]
        self.assertNotEqual(mid[1], 0.0, "曲线中点应偏离直线")

    def test_steps_zero_is_safe(self):
        # 除零保护：steps=0 视为 1 步（起点+终点两个点）
        pts = hc.curve_points((1, 1), (2, 2), (3, 3), 0)
        self.assertEqual(len(pts), 2)
        self.assertEqual(pts[0], (1, 1))
        self.assertEqual(pts[-1], (3, 3))


class MoveAndClickTests(unittest.TestCase):
    def test_moves_then_down_up(self):
        page = _FakePage()
        with mock.patch.object(hc.time, "sleep"):
            ok = hc.move_and_click(page, _FakeBox(page._box))
        self.assertTrue(ok)
        self.assertGreater(len(page.mouse.moves), 10, "应分多步移动")
        self.assertEqual(page.mouse.downs, 1)
        self.assertEqual(page.mouse.ups, 1)
        x, y = page.mouse.moves[-1]
        self.assertGreaterEqual(x, page._box["x"])
        self.assertLessEqual(x, page._box["x"] + page._box["width"])

    def test_lands_inside_box_not_on_edge(self):
        page = _FakePage()
        with mock.patch.object(hc.time, "sleep"):
            hc.move_and_click(page, _FakeBox(page._box), jitter=8)
        x, y = page.mouse.moves[-1]
        self.assertGreater(x, page._box["x"] + 1.5)
        self.assertLess(x, page._box["x"] + page._box["width"] - 1.5)

    def test_missing_box_returns_false(self):
        page = _FakePage()
        self.assertFalse(hc.move_and_click(page, _FakeBox(None)))

    def test_scroll_failure_falls_back_to_js(self):
        class Bad(_FakeBox):
            def scroll_into_view_if_needed(self, timeout=None):
                raise RuntimeError("timeout")

            def evaluate(self, js):
                return "scrolled"

        page = _FakePage()
        with mock.patch.object(hc.time, "sleep"):
            self.assertTrue(hc.move_and_click(page, Bad(page._box)))

    def test_no_mouse_down_is_not_counted_as_success(self):
        class Broken(_FakeBox):
            def __init__(self, box):
                super().__init__(box)
                self.page = None

        page = _FakePage()

        def boom():
            raise RuntimeError("no mouse")

        page.mouse.down = boom
        with mock.patch.object(hc.time, "sleep"):
            self.assertFalse(hc.move_and_click(page, _FakeBox(page._box)))


class HumanTypeTests(unittest.TestCase):
    def test_types_every_char(self):
        loc = _FakeBox({"x": 0, "y": 0, "width": 1, "height": 1})
        typed = []
        loc.type = lambda ch, delay=0: typed.append(ch)
        with mock.patch.object(hc.time, "sleep"):
            self.assertTrue(hc.human_type(loc, "内容港"))
        self.assertEqual("".join(typed), "内容港")

    def test_returns_false_on_error(self):
        loc = _FakeBox({"x": 0, "y": 0, "width": 1, "height": 1})

        def boom(ch, delay=0):
            raise RuntimeError("lost focus")

        loc.type = boom
        with mock.patch.object(hc.time, "sleep"):
            self.assertFalse(hc.human_type(loc, "x"))


class PickOptionTests(unittest.TestCase):
    def test_picks_by_text(self):
        picked = {}

        class Locs:
            def count(self):
                return 2

            def nth(self, i):
                labels = ["前端", "Playwright"]
                loc = _FakeBox({"x": 10, "y": 10 * i, "width": 40,
                                 "height": 18})

                def inner_text():
                    return labels[i]

                loc.inner_text = inner_text
                return loc

        page = _FakePage()

        def fake_click(pg, loc, **kw):
            if hasattr(loc, "inner_text"):
                picked["label"] = loc.inner_text()
            return True

        control = _FakeBox(page._box)
        with mock.patch.object(hc, "move_and_click", fake_click), \
                mock.patch.object(hc, "_visible_options", lambda p: Locs()), \
                mock.patch.object(hc.time, "sleep"):
            label = hc.pick_option(page, control, text="Playwright")
        self.assertEqual(label, "Playwright")
        self.assertEqual(picked["label"], "Playwright")

    def test_returns_none_when_no_options(self):
        class Locs:
            def count(self):
                return 0

        page = _FakePage()
        with mock.patch.object(hc, "move_and_click", lambda *a, **k: True), \
                mock.patch.object(hc, "_visible_options", lambda p: Locs()), \
                mock.patch.object(hc.time, "sleep"):
            self.assertIsNone(hc.pick_option(page, object()))
            self.assertIsNone(hc.pick_option(page, object()))

    def test_control_click_failure_returns_none(self):
        class Locs:
            def count(self):
                return 1

        page = _FakePage()
        with mock.patch.object(hc, "move_and_click", lambda *a, **k: False):
            self.assertIsNone(hc.pick_option(page, object()))


class BoundaryMarkerTests(unittest.TestCase):
    """约定测试：本模块的每个宽异常都必须带 # aqg: top-level boundary 标记。

    这是仓库级硬门禁（构建检查会拦），用测试锁住，避免以后新增 except 时
    忘了加标记导致 CI/checker 阻塞。
    """

    def _source_lines(self):
        src = Path(hc.__file__).read_text(encoding="utf-8")
        return src.splitlines()

    def test_every_broad_except_has_boundary_marker(self):
        lines = self._source_lines()
        offenders = []
        for i, ln in enumerate(lines):
            if ln.strip().startswith(("except Exception", "except BaseException")):
                window = lines[max(0, i - 5):i]
                if not any("aqg: top-level boundary" in w for w in window):
                    offenders.append(i + 1)
        self.assertEqual(offenders, [],
                         "这些宽异常上方 5 行内没有 # aqg: top-level boundary 标记：%s"
                         % offenders)

    def test_module_docstring_states_what_it_does_not_do(self):
        text = Path(hc.__file__).read_text(encoding="utf-8")
        self.assertIn("验证码", text)
        self.assertIn("不做", text, "模块须写明刻意不做什么（防检测/破解验证码）")


if __name__ == "__main__":
    unittest.main()
