# Phase 5 交付清单 · 全局整合与最终收口

> 交付物：`d3_dashboard.offline.html`（完全离线单文件，491 KB）
> 开发版：`d3_dashboard.html`（219 KB，保留 CDN 异步加载器）
> 状态：**六层验证全绿** · 截图 6 张 · 断网对照实验通过
---

## 一、四项收口工作

### A. 全局导航与阅读节奏

| 组件 | 实现 | 技术要点 |
|---|---|---|
| **阅读进度条** | `#progress` 顶部 2px 渐变色条 | `scaleX` 直写（transform 走合成线程，不触发重排）；不用 transition，避免与 rAF 写入互相追尾 |
| **侧栏目录** | `#toc`，174px，`≥1280px` 启用 | `position:fixed`（不用 sticky：本页图表容器带 overflow 上下文）；`top:44px` |
| **角落折叠目录** | `#toc-mini`（`<details>`），`<920px` 启用 | 右下角，`backdrop-filter:blur`；跳转后自动收起 |
| **中间档** | `920–1279px` | **两者都不显示** —— 留白比塞一个拥挤的导航更干净 |
| **滚动高亮** | scroll-spy，`.cur` 当前章 + `.done` 已读章 | 判定用「触发线(90px)穿过区间」，**不用 IO ratio**（区块高度差 2×，ratio 阈值会失灵） |
| **视觉呼吸空间** | `.panel + .panel{margin-top:52px}` + `::before` 320px 居中渐变分割线 | 窄屏按比例收到 38px |
| **章节罗马编号** | `.sec-index` 内 `I`–`V` | 五章成为目录可引用的真实锚点 |

滚动性能三纪律：监听 `passive:true` → 回调只写标记 → 测量全推迟到 rAF（一帧最多算一次）。

### B. 跨区块叙事联动（2 处）

| # | 位置 | 颜色语义 | 文案核心 |
|---|---|---|---|
| ① | `#sec-space` 段首 `<p>` 之后、主图 mini-cap 之前<br>（第 1033 行 `.thread.thread-meso`） | 紫 `--inst` ↔ 呼应第 II 章器乐轨 | 「**1960s 为什么在这里一跤跌倒？** 器乐与人声在 1950s–1970s 是**平行下坠**的，两条一起塌，合起来才够粗…同一个七年，在两章里是同一件事的两种读法：那边读的是**两条路的分家**，这边读的是**坐标平面上的一跤**」<br>链接 → `#sec-meso` |
| ② | `#sec-micro` 副图 legend 之后、readouts 之前<br>（第 933 行 `.thread.thread-macro`） | 品红 `--micro` ↔ 呼应第 I 章宏观 | 「**一个世纪在 170,653 首歌上的走势，被一首歌重演了一遍**…跌得最狠的十年同样是 1980s，回升的十年同样是 2000s 之后」<br>链接 → `#sec-macro`，对照世纪降幅 −72.6% |

### C. 数据底座与法医学声明（第 V 章 `#sec-forensic`）

四条防线排成 **2×2**（非 auto-fit 3+1 —— 972px 内宽最多容 3 列，第 4 张孤零折行会像"补充说明"，与并列地位不符）：

| 卡 | 大数字 | 内容 |
|---|---|---|
| 防线一 · 单一数据底座 | **10** 个锁定视图 | 前端零硬编码污染；每视图六类断言（行数/字段/类型/空值/唯一/值域） |
| 防线二 · 前提污染清除 | **5** 首 + **16** 条 | 剔除 5 首泛用名污染曲目；16 条物理不可能年份（唱片发行日冒充录音年，全部落在 1932–1949） |
| 防线三 · 聚合粒度校正 | **0.64 / 0.17** | ICC 修正聚合粒度偏差；早期 0.88/0.49 是格均值上的 η²（漏 k̄ 校正 + 抹掉层内方差） |
| 防线四 · 薄格子强制降级 | **15 / 81** 格 | n≤2 空心点+虚线；19 格无记录直接断开、不插值 |

另附「三条易忽略口径」+ **四层验证运行记录表**（等宽数字对齐，像体检单）。

> ⚠️ **数字更正**：指令里写「12 条物理不可能年份」，台账实为 **16 条**。已按台账真值写。

### D. 性能与最终打包

- **性能**：scroll 三纪律；`setActive` 状态未变则不碰 DOM；ResizeObserver 表驱动 + 宽度未变跳过
- **体积核查**：数据块仅 **25.3 KB（11.8%）**，最大 `SVC_SONGS` 12.3 KB。主体是中文注释（文档价值）。SQL 层已 round 到展示精度 → 无二次舍入可去
- **离线方案**：`verify/build5.py` 把 CDN 加载器整段换成内联 D3 v7.9.0 + **保留 `window.__onD3Ready` 同签名契约** → **主脚本一行不改**（改动面最小、回归风险最低）；同时删除 2 处 `preconnect`

---

## 二、四项交付验证

### ① 单文件体积与离线运行确认 ✅

```
d3_dashboard.html            224,302 字节 ( 219.0 KB)  CDN 依赖版
d3_dashboard.offline.html    502,843 字节 ( 491.1 KB)  完全离线单文件
```

**断网对照实验**（`verify/offline5.py`，`--host-resolver-rules` 黑洞 + 代理黑洞）：

| 被测文件 | 预期 | 实测 |
|---|---|---|
| CDN 依赖版 | 必须失败 | fallback 7 处、完整 SVG **0 个** ✅（证明断网确实生效） |
| 内联离线版 | 必须成功 | fallback 渲染元素 **0 个**、五个图表容器 SVG **5/5** ✅ |

两条同时成立 —— 离线能力来自内联，不是"网络恰好通"。

### ② TOC 与滚动高亮截图证明 ✅

`verify/_work/cap5/`（6 张）：

| 文件 | 内容 |
|---|---|
| `P5_01_全页_1440.png` | 全页 2600px —— 整体节奏、区块呼吸、侧栏目录 + 进度条 + 角落导航同框 |
| `P5_02_侧栏目录_1440.png` | 宽屏导航形态 + **高亮态**（第 IV 章亮、前三章 `.done` 弱化） |
| `P5_03_声明区块_1440.png` | 2×2 四卡 + 三条口径 + 四层验证表 |
| `P5_04_角落目录_478.png` | 窄屏形态（侧栏隐藏、右下折叠 pill、罗马编号、进度条） |
| `P5_05_穿针引线1_1440.png` | Phase 4 → Phase 2（紫色系） |
| `P5_06_穿针引线2_1440.png` | Phase 3 → Phase 1（品红系） |

### ③ 跨区块联动文案与位置清单 ✅

见上文「B. 跨区块叙事联动」表。均为真实 `<a href="#sec-...">` 锚点跳转，非纯文字提示。

### ④ 全量回归测试 ✅

| 层 | 脚本 | 结果 |
|---|---|---|
| L1 数据层 | `verify/lv10.py` | **10/10** 全绿 |
| L2a 源码 Phase1-3 | `verify/check3.py` | ALL PASS |
| L2b 源码 Phase4 | `verify/check4.py` | ALL PASS |
| L3a 渲染 Phase1-3 | `verify/render_check.py` | ALL PASS（三宽度 × 六类） |
| L3b 渲染 Phase4 | `verify/render_check4.py` | ALL PASS（三宽度 × 八类） |
| L4a 交互 tooltip | `verify/probe4.py` | ALL PASS |
| L4b 交互 导航 | `verify/probe5.py` | ALL PASS（P1–P8） |
| L5 离线渲染 | `verify/offline5.py` | ALL PASS |

Phase 4 几何断言在 Phase 5 改动后**逐项未变**：

```
1440px  点11 椭圆11 条11 路径12 | 线宽 1950→60=7.93 1960→70=8.00 1980→90=1.00 (7.9×) | 越界0 文字重叠0 点压盖0
 900px  点11 椭圆11 条11 路径12 | 同上
 478px  点11 椭圆11 条11 路径12 | 同上
```

---

## 三、本轮排查出的真问题（非 Phase 5 引入）

### 问题 1：`check3.py` 四条断言是 Phase 3 的过期期望值

全量回归首次报 4 项 FAIL，一度误判为「Phase 5 破坏了回归」。逐条查原文后确认**全是陈旧断言**：

| 断言 | 旧期望 | 现状（正确） |
|---|---|---|
| `loadingEl.remove()` 次数 | 4 | **6**（7 个容器中 mesoShape 只是往 chart-meso 里 append 子 SVG，无独立 loading 节点） |
| fallback 覆盖容器 | 5 个 | **7 个**（+space / +space-corr） |
| footer 文案 | `Phase 3` | **`Phase 5`**（本就被要求更新） |
| `#sec-space` | 仍为 placeholder | **已升级为正式区块**（Phase 4 交付） |

修法：改为断言当前正确状态 + 注释写清为什么变；并新增两条前瞻断言。

### 问题 2：headless 下 rAF 在虚拟时间耗尽前不触发 ⭐⭐

`probe5` 第一版用 `window.scrollTo` 驱动，全盘"失效"。根因两层：
1. `scrollTo` 在 headless 下**静默无效**，`pageYOffset` 恒为 0
2. `requestAnimationFrame` 回调**要等 `--virtual-time-budget` 耗尽、快照那刻才补跑** —— 输出里有 `RAF_FIRED`，但读到它时它还没跑

而页面的进度条/scroll-spy **恰好完全跑在 rAF 里**（这是正确做法）→ 用滚动驱动必然测不到。

修法：探针内把 `pageYOffset` 与 `requestAnimationFrame` 都换成可手动推进的桩，`setY()` 后 `flushRaf()`；"真机表现"交给 `--screenshot`（另一条渲染路径，出图前 rAF 已完成）。

### 问题 3：探针自身断言口径写反 3 处

- P5 要求五项**全部**高亮（等于要求所有章节同时亮）→ 应判「**恰好**目标章亮、其余不亮」
- P6 点完链接又 `setY(0)`，当场覆盖点击结果 → 应只点、不跟滚动
- 用物理滚动位置断言"跳转成功" → 改断言状态变化

### 问题 4：声明区 4 卡 3+1 折行

`auto-fit minmax(238px,1fr)` 在 972px 内宽下最多 3 列 → 第 4 张孤零折到第二行，视觉上像"多出来的补充说明"。改为 **2×2 固定两列**，窄屏（≤700px）单列。

---

## 四、复现命令

```bash
cd "E:\产品\曲风数据分析"

# 构建离线单文件（含产物校验）
.venv/Scripts/python.exe verify/build5.py

# 六层回归
.venv/Scripts/python.exe verify/lv10.py            # L1 数据层
.venv/Scripts/python.exe verify/check3.py          # L2a 源码 Phase1-3
.venv/Scripts/python.exe verify/check4.py          # L2b 源码 Phase4
.venv/Scripts/python.exe verify/render_check.py    # L3a 渲染 Phase1-3
.venv/Scripts/python.exe verify/render_check4.py   # L3b 渲染 Phase4
.venv/Scripts/python.exe verify/probe4.py          # L4a tooltip 探针
.venv/Scripts/python.exe verify/probe5.py          # L4b 导航探针
.venv/Scripts/python.exe verify/offline5.py        # L5 断网对照

# 证据截图
.venv/Scripts/python.exe verify/cap5.py
```

> ⚠️ 跑任何 DOM 相关脚本前先 `rm -f verify/_work/p4_dom_*.html verify/_work/p5_probe_*.html`，
> 否则会读到上一版的缓存状态（本轮已两次踩到）。
