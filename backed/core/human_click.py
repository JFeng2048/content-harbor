# -*- coding: utf-8 -*-
"""拟人化输入：给"只有真实鼠标事件才认"的自定义控件用。

为什么需要它：掘金的标签/话题选择器是字节系 byte-select，候选列表挂在
teleport 容器里，Playwright 的可行动性检查点不动它，JS 派发的 click 组件
又不认（组件只处理真实的 mousedown/mouseup 序列）。人能用鼠标选中，脚本就得
把鼠标走一遍。

做什么：
  - 滚动到可视 → 取包围盒 → 贝塞尔曲线分步移动 → 停顿 → down → 抬起
  - 打字按字符带随机间隔，长文本比短文本慢
  - 自定义下拉的"选中候选项"封装（开 → 等候选 → 悬停 → 点）

刻意不做：
  - 不做指纹伪装 / 反检测绕过（那是浏览器层的事，不在这里掺和）
  - 不碰验证码：验证码一律人工 handoff（core/browser.py 的既有约定）
"""

import math
import random
import time

__all__ = ["curve_points", "move_and_click", "human_type", "pick_option",
           "OPTION_SELECTORS"]

# 常见候选项容器（字节系 / 通用 / antd）
OPTION_SELECTORS = (
    ".byte-select-option:not(.byte-select-option-empty)",
    "[role=option]:not([aria-disabled=true])",
    "[class*=dropdown] [class*=option]:not([class*=empty])",
    "li[class*=option], [class*=suggest] li, [class*=menu] li",
)


def curve_points(start, control, end, steps):
    """二次贝塞尔采样。steps+1 个点，起点终点精确，中间带弧度。

    steps < 1 视为 1（除零保护：调用方可能算出 0 步）。
    """
    steps = max(1, int(steps))
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = (u * u * start[0] + 2 * u * t * control[0] + t * t * end[0])
        y = (u * u * start[1] + 2 * u * t * control[1] + t * t * end[1])
        pts.append((x, y))
    return pts


def move_and_click(page, locator, hold_ms=(60, 150), steps=(12, 24),
                   jitter=8, timeout=15000, settle_ms=(250, 700)):
    """把鼠标沿曲线移到元素中心附近并点击。返回是否点成功。

    不抛异常：点不到就返回 False，调用方决定是否换候选/兜底。
    """
    try:
        locator.scroll_into_view_if_needed(timeout=timeout)
    # aqg: top-level boundary 滚动失败不致命：换 JS 滚动再试，元素本来可能在虚拟滚动容器里
    except Exception:
        # 元素在虚拟滚动容器里时 scroll_into_view 可能超时，退回 JS 滚动
        try:
            locator.evaluate("el => el.scrollIntoView({block:'center'})")
        # aqg: top-level boundary 拿不到包围盒就返回 False 交调用方兜底，不让点击异常上抛打断后续降级
        except Exception:
            return False
    time.sleep(0.25)
    try:
        box = locator.bounding_box()
    # aqg: top-level boundary 滚动与取盒都可能抛，一并降级为 False（本函数的契约就是不抛）
    except Exception:
        return False
    if not box:
        return False
    # 落点：中心 + 随机偏移，且不贴边（贴边常被判定为非人工命中）
    cx = box["x"] + box["width"] / 2 + random.uniform(-jitter, jitter)
    cy = box["y"] + box["height"] / 2 + random.uniform(-jitter, jitter)
    cx = min(max(cx, box["x"] + 2), box["x"] + box["width"] - 2)
    cy = min(max(cy, box["y"] + 2), box["y"] + box["height"] - 2)
    start = (max(0.0, cx - random.uniform(120, 320)),
             max(0.0, cy + random.uniform(60, 220)))
    ctrl = ((start[0] + cx) / 2 + random.uniform(-90, 90),
            (start[1] + cy) / 2 - random.uniform(40, 160))
    n = random.randint(*steps)
    for x, y in curve_points(start, ctrl, (cx, cy), n):
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.004, 0.013))
    time.sleep(random.uniform(0.03, 0.12))
    try:
        # aqg: top-level boundary 鼠标按下失败说明驱动层已断，返回 False 比抛异常更好定位
        page.mouse.down()
    except Exception:
        return False
    time.sleep(random.uniform(*hold_ms) / 1000.0)
    try:
        page.mouse.up()
    # aqg: top-level boundary 鼠标按下失败说明驱动层已断，返回 False 比抛异常更好定位
    except Exception:
        return False
    time.sleep(random.uniform(*settle_ms) / 1000.0)
    return True


def human_type(locator, text, per_char=(45, 130), pause_every=12,
               pause_ms=(120, 400)):
    """逐字符输入，带随机间隔；每 pause_every 个字符多喘一口。"""
    ok = True
    for i, ch in enumerate(text):
        try:
            locator.type(ch, delay=random.randint(*per_char))
        # aqg: top-level boundary 打字中途可能失焦，返回 False 让调用方知道要重新聚焦
        except Exception:
            ok = False
            break
        if pause_every and (i + 1) % pause_every == 0:
            time.sleep(random.uniform(*pause_ms) / 1000.0)
    return ok


def pick_option(page, control, index=0, text=None, wait_ms=2500,
                poll_ms=200, timeout_ms=9000):
    """打开自定义下拉并选中一个候选项。

    control  : 下拉触发器 locator
    index    : 候选项序号（text 为 None 时用）
    text     : 期望的候选文本（优先按文本找，找不到再按序号）
    返回选中的候选文本；没选到返回 None。
    """
    if not move_and_click(page, control, timeout=9000):
        return None
    deadline = time.time() + wait_ms / 1000.0
    locs = None
    while time.time() < deadline:
        locs = _visible_options(page)
        if locs.count() > 0:
            break
        time.sleep(poll_ms / 1000.0)
    if locs is None or locs.count() == 0:
        return None
    target = None
    if text:
        for i in range(locs.count()):
            try:
                if text in (locs.nth(i).inner_text() or ""):
                    target = locs.nth(i)
                    break
            # aqg: top-level boundary 读候选项文本失败不应中断选中流程
            except Exception:
                continue
    if target is None:
        idx = min(index, locs.count() - 1)
        target = locs.nth(idx)
    label = ""
    try:
        label = (target.inner_text() or "").strip()[:24]
    # aqg: top-level boundary 候选项逐个试读文本，个别读不到就跳过
    except Exception:
        pass
    move_and_click(page, target, timeout=9000)
    return label or "(未取到文本)"


def _visible_options(page):
    """把几种候选选择器合并成一个 locator（visible 过滤）。"""
    sel = ", ".join(s + ":visible" for s in OPTION_SELECTORS)
    try:
        return page.locator(sel)
    # aqg: top-level boundary 合并选择器失败时退到最朴素的 li:visible，不让下拉点击整体失败
    except Exception:
        return page.locator("li:visible")
