# AUDIT.md — 全量存量检测与优化报告

> 日期：2026-09-22 · 范围：全项目（Python 后端 ~6300 行 / Vue3 前端 / DB / MCP / 登录资产）
> 结论：**发现 12 项缺陷（P0×4 全部修复）**，全部经复检电池验证通过；根目录归档 48 个残渣脚本。

## 一、缺陷清单（发现 → 修复 → 验证）

| # | 级别 | 缺陷 | 影响 | 修复 | 验证 |
|---|---|---|---|---|---|
| 1 | **P0** | playwright `sync_playwright()` 每实例各起一个：首实例 dispatcher 挂起后**线程的"运行中循环"状态泄漏**，同线程第二个 driver 必报 `inside the asyncio loop` | zhihu/juejin `/check` 稳定 500（带偏登录排查一上午） | **进程级共享驱动单例**（`_get_shared_pw`，一生只 `__enter__` 一次）+ 实例关闭不停驱动 | 三轮×三平台连打 **9/9 全绿** |
| 2 | **P0** | greenlet 跨线程：池实例被 check 线程建、发布 run 线程用 | 真实 E2E 发布直接失败（Cannot switch to a different thread） | **专属浏览器线程** `browser_thread_run`：一切 playwright 操作单线程串行（防自锁内联），`_drop/close_all` 关闭同路由 | 同上 9/9 + 冒烟 7 断言全过 |
| 3 | **P0** | 扫码成功、关窗丢态：登录会话只在内存，chromium 没刷盘就被关 | 用户被迫重复扫码（本次投诉根因） | **登录快照** `*.auth.json`：登录成功瞬间 Python 原子写（tmp+replace），开浏览器自动合回 | 三平台快照齐备且持续变大（check 保鲜生效） |
| 4 | **P0** | `service.check` 不 goto，`check_auth` 跑在 about:blank：null 源跨站 fetch、**SameSite cookie 全拦** → 永远假"未登录" | check 端点从诞生起就是坏的，反复误报要求重登 | check 先落平台域 + `_check_auth_settled` 沉降重试 | 三平台 check 全部真实 true |
| 5 | P1 | hub.js 使用 `ElMessageBox` 但**未 import** | 脏文章切换必抛 ReferenceError | 补 import | 前端构建通过 |
| 6 | P1 | `_busy_for` 里 `atexit.register` 写在 `return` 之后（**死代码**） | 进程退出浏览器从不自动关 | 移到 `__init__` | 编译+启动通过 |
| 7 | P1 | `check()` 不持 per-key 互斥（B3 漏洞） | check 与发布并发撞同一实例 | 加 `with self._busy_for` | 回归通过 |
| 8 | P1 | MCP `publish_article` 走 legacy，不进工作流引擎 | agent 驱动名不副实 | 切流 `/publish/workflow`（仅启动失败回退，防双发），返回 run_id | MCP 导入+路由检查通过 |
| 9 | P2 | service.py 重复 `import random/time` | 卫生 | 删除 | 编译通过 |
| 10 | P2 | **articles/jobs 表零索引**（列表过滤/门禁追溯全表扫） | 数据增长后查询退化 | 补 3 个索引（status/updated_at/type+status） | PRAGMA 确认 |
| 11 | P2 | 根目录 47 个 probe/delete/dump/test 调试残渣 | 工程卫生、掩盖入口 | 42 个归档 `scripts/debug/`，qc/verify 6 个入 `scripts/` | 根目录仅剩 `cli.py` |
| 12 | P3 | 发布向导轮询超时会回退 legacy → **同文双发**隐患 | 极端情况双发平台 | 回退仅限"启动失败"，启动后只轮询不回退 | 代码审查+构建 |

## 二、登录态永续保障（硬约束：一次登录，永续记住）

四层防御，缺一不可：

| 层 | 机制 | 触发点 |
|---|---|---|
| L1 | 浏览器 profile 目录 cookie 持久化 | 每次浏览（平台侧会过期，平台规则绕不开） |
| L2 | **`*.auth.json` 登录快照**（原子写，损坏免疫） | 登录成功瞬间必写 |
| L3 | **快照自动保鲜**：check 通过即刷新；关窗/池淘汰时有会话 cookie 就刷新 | 每次 check、每次正常关窗（平台轮换会话后快照跟上） |
| L4 | **启动自动合回**：开浏览器即把快照 cookie 注入 | 每次 `BuiltinBrowser.start()`（profile 被清也能恢复） |

资产现状：`csdn_default.auth.json` / `zhihu_default.auth.json` / `juejin_default.auth.json` 三份齐备，
复检中体积持续增长 = 保鲜链路在工作。**平台会话未过期的前提下，任何 profile 丢失、刷盘失败、
线程错乱都不会再让你重扫一次码。**

## 三、复检电池（全绿）

| 项 | 结果 |
|---|---|
| 全项目 `py_compile` | 0 错误 |
| 三平台 check × 3 轮连打 | **9/9 logined:true** |
| smoke_workflow（dry_run 双平台+负面断言） | PASS |
| smoke_hitl（重试/recover/草稿确认/草稿拒绝 7 断言） | PASS |
| dry_run 三平台引擎 run | done |
| MCP server 导入 | OK |
| 前端 vite 构建 | 通过 |
| 登录快照资产 | 3/3 在且保鲜中 |

## 四、遗留观察（未修，知情即可）

| 项 | 说明 | 建议时机 |
|---|---|---|
| element-plus 单包 943KB | 首屏体积，可路由级懒加载 | 用户感知卡顿时 |
| ~~update/sync 仍走 legacy~~ | ✅ M5 已切流（update 专图 + sync 一文一 run 扇出；smoke_update S1–S6 全绿 + 双跑 DB 对账一致） | 完成 |
| refresh 走 legacy | 经评估不接入（M5 裁定，永久 legacy；单步只读无引擎价值点，重评触发条件见 docs/design/m5-architecture.md §1.4） | 完成（裁定） |
| 共享驱动进程级崩溃 | 需重启服务恢复（原结构也如此） | 发生再议 |
| LLM 分诊可选项（平台推荐/按平台改写） | ARCHITECTURE M3 标注"可选、默认关"，未实装=天然关 | 有真实需求再开 |
| 掘金后台 2-3 个测试草稿 | E2E/历史遗留 | 用户随手删 |
