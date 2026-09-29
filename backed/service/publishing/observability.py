# -*- coding: utf-8 -*-
"""可观测性：结构化日志 + 指标 + 发布链路 trace。

定位：2026 生产水位的最小可观测层。纯标准库，不引 opentelemetry/prometheus
这类重依赖——单机 SQLite 服务用不上分布式追踪，RotatingJSON 日志 + 内存指标
 + 一次发布的 trace 快照足够排障，且能直接喂给任何 grep/jq 管道。

三块能力：
  1. 结构化日志 —— RotatingJSON，每次发布/登录/验证码命中落一条 JSON 行到
     data/observability/events.log，带 trace_id 串联整条发布链路。
  2. 指标 —— 内存计数器，进程内累积，/metrics 端点实时拉取（重启归零，
     长期趋势看 jobs 表 + events.log）。
  3. 发布链路 trace —— 一次 publish/update 的所有平台子步骤串进同一
     trace_id，事后看"哪个平台卡在哪、耗时多少"一目了然。

线程安全：计数器加锁。事件日志走 RotatingFileHandler 自带线程锁。
"""

import json
import logging
import os
import threading
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OBS_DIR = DATA / "observability"
EVENT_LOG = OBS_DIR / "events.log"

# 单文件 10MB，留 5 份备份；发布链路是低频事件，一年也不会撑爆
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP = 5


# ---------------------------------------------------------------------------
# 结构化事件日志
# ---------------------------------------------------------------------------
def _build_event_logger() -> logging.Logger:
    logger = logging.getLogger("hub.events")
    if logger.handlers:  # 已被建过（热重载/重 import）
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    OBS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fh = RotatingFileHandler(str(EVENT_LOG), maxBytes=_MAX_BYTES,
                                 backupCount=_BACKUP, encoding="utf-8")
    except Exception:
        fh = logging.FileHandler(str(EVENT_LOG), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    return logger


_event_logger = _build_event_logger()


def emit(event: str, **fields):
    """落一条结构化事件。自动补 ts/level/pid，trace_id 透传。"""
    rec = {"ts": time.time(), "event": event, "level": fields.pop("level", "info"),
           "pid": os.getpid()}
    rec.update(fields)
    try:
        _event_logger.info(json.dumps(rec, ensure_ascii=False, default=str))
    except Exception:
        # 日志本身不该影响主流程
        pass
    return rec


# ---------------------------------------------------------------------------
# 指标（内存计数器）
# ---------------------------------------------------------------------------
class MetricRegistry:
    """计数器 + 直方图。线程安全，进程内累积。

    用法：
        METRICS.incr("publish.ok")
        METRICS.observe("publish.dur", 3.2)
        METRICS.snapshot()  # -> {name: value}
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._counters = {}
        self._gauge = {}
        self._hist = {}   # name -> {"sum": float, "n": int, "buckets": {label: int}}
        # 固定分桶，覆盖"快/慢/崩"三档
        self._BUCKETS = [0.5, 1, 2, 5, 10, 30, 60, float("inf")]

    def incr(self, name: str, delta: int = 1):
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + delta

    def gauge(self, name: str, value: float):
        with self._lock:
            self._gauge[name] = value

    def observe(self, name: str, value: float):
        """记录一次耗时（秒），进固定分桶。"""
        with self._lock:
            h = self._hist.setdefault(name, {"sum": 0.0, "n": 0, "buckets": {}})
            h["sum"] += value
            h["n"] += 1
            for b in self._BUCKETS:
                if value <= b:
                    label = str(b) if b != float("inf") else "+Inf"
                    h["buckets"][label] = h["buckets"].get(label, 0) + 1
                    break

    def snapshot(self) -> dict:
        with self._lock:
            out = {"counters": dict(self._counters),
                   "gauge": dict(self._gauge),
                   "histograms": {}, "updated_at": time.time()}
            for name, h in self._hist.items():
                out["histograms"][name] = {
                    "count": h["n"],
                    "sum": h["sum"],
                    "avg": (h["sum"] / h["n"]) if h["n"] else 0.0,
                    "max": h.get("max", 0.0),
                    "buckets": dict(h["buckets"]),
                }
            # 顺手记一次 max
            for name, h in self._hist.items():
                if "max" not in h:
                    h["max"] = 0.0
                # observe 时已维护 max
            return out

    # 让 observe 顺手维护 max
    def _observe_with_max(self, name, value):
        with self._lock:
            h = self._hist.setdefault(name, {"sum": 0.0, "n": 0, "buckets": {}, "max": 0.0})
            h["sum"] += value
            h["n"] += 1
            h["max"] = max(h.get("max", 0.0), value)
            for b in self._BUCKETS:
                if value <= b:
                    label = str(b) if b != float("inf") else "+Inf"
                    h["buckets"][label] = h["buckets"].get(label, 0) + 1
                    break


# 修正：observe 内部统一走 _observe_with_max 语义（上面 observe 已分桶，补 max）
_orig_observe = MetricRegistry.observe


def _observe_patched(self, name, value):
    _orig_observe(self, name, value)
    with self._lock:
        h = self._hist.get(name)
        if h is not None:
            h["max"] = max(h.get("max", 0.0), value)


MetricRegistry.observe = _observe_patched

METRICS = MetricRegistry()


# ---------------------------------------------------------------------------
# 发布链路 trace
# ---------------------------------------------------------------------------
class TraceContext:
    """一次 publish/update 的全链路 trace。

    用法：
        with TraceContext("publish", article_id=3, platforms=["csdn","juejin"]) as t:
            ...每个平台子步骤调 t.step("csdn.publish", dur=2.1, ok=True)
        # 退出时 t.commit() 把整条 trace 落 events.log 一条

    单条 trace 控制在合理行数内（平台数 × 每平台 1-3 step），不会膨胀。
    """

    def __init__(self, op: str, **ctx):
        self.op = op
        self.trace_id = uuid.uuid4().hex[:12]
        self.started = time.time()
        self.ctx = ctx
        self.steps = []

    def step(self, name: str, dur: float = 0.0, ok: bool = True, detail: str = ""):
        self.steps.append({"name": name, "dur": round(dur, 3),
                           "ok": ok, "detail": detail[:200]})
        METRICS.incr(f"{self.op}.step.{ 'ok' if ok else 'fail' }")
        if ok:
            METRICS.incr(f"{self.op}.ok")
        else:
            METRICS.incr(f"{self.op}.fail")

    def commit(self):
        dur = round(time.time() - self.started, 3)
        ok = all(s["ok"] for s in self.steps) if self.steps else True
        emit("trace", trace_id=self.trace_id, op=self.op,
             trace_ok=ok, duration=dur, steps=self.steps, **self.ctx)
        METRICS.observe(f"{self.op}.dur", dur)
        return self.trace_id

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *a):
        if exc_type is not None:
            self.step(f"{self.op}.exc", dur=0, ok=False, detail=str(exc_type)[:120])
        self.commit()
        return False


# ---------------------------------------------------------------------------
# 便捷指标名（避免散落字符串）
# ---------------------------------------------------------------------------
M_PUBLISH = "publish"
M_UPDATE = "update"
M_LOGIN = "login"
M_AI = "ai"
M_CAPTCHA = "captcha"
M_API = "api"


def begin_api_trace(method: str, path: str) -> TraceContext:
    t = TraceContext("api", method=method, path=path)
    return t
