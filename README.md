# 世纪声学漂流史 · 法医级音乐数据叙事看板

> **一句话定位**：把 170,653 条 Spotify 曲目（1921–2020）还原成一部「世纪声学漂流史」——
> 每一个数字都来自**可复算的锁定视图**，每一条叙事结论都被**机器断言逐值证伪或确认**，
> 前端**零硬编码**。

<p>
<img alt="Python" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
<img alt="DuckDB" src="https://img.shields.io/badge/DuckDB-view%20layer-FFF000?logo=duckdb&logoColor=black">
<img alt="D3" src="https://img.shields.io/badge/D3.js-v7-F9A03C?logo=d3.js&logoColor=white">
<img alt="offline" src="https://img.shields.io/badge/offline-single%20file%20491KB-2ea44f">
<img alt="tests" src="https://img.shields.io/badge/verify-8%20layers-blue">
</p>

---

## 0. 三分钟上手（不用装任何东西）

| 你想看什么 | 怎么做 |
|---|---|
| **看最终成品** | 直接用浏览器打开 [`d3_dashboard.offline.html`](d3_dashboard.offline.html)（≈491 KB 单文件，**零外部请求、断网也能跑**） |
| **看它凭什么可信** | 读 [§4 如何验证](#四如何验证一键复跑-8-层自动化测试)，一键复跑 8 层测试 |
| **看结论** | 读 [§3 核心统计发现](#三核心统计发现) |

---

## 一、项目概述

| 项 | 内容 |
|---|---|
| 产品 | 法医级音乐数据叙事看板（D3 单页可视化） |
| 核心命题 | 用「数据法医学」的方法，证明流行音乐的声学特征（原声度 / 能量）在百年间发生了**可被量化、可被证伪**的结构性漂移 |
| 技术栈 | Python 3.13 + DuckDB（视图层数据底座）· D3.js v7（内联，零运行时依赖）· 原生 HTML/CSS/JS 单文件 · Headless Edge（自动化验证） |
| 形态 | 双形态交付——`d3_dashboard.html`（CDN 依赖版，便于开发）与 `d3_dashboard.offline.html`（**完全离线单文件，零外部请求**，用于提交/演示） |
| 交付哲学 | **数据即代码**：10 个视图口径锁定为可执行 Python；前端所有数字从视图实查后注入，不手抄、不魔数 |

---

## 二、数据底座声明

### 2.1 数据规模（真实摄取，未裁剪）
- 原始样本：**170,653 行 × 19 列**（Spotify 曲目级音频特征，年份覆盖 1921–2020，100 个取值年）。
- 第一道闸门 `data_fingerprint_check`：对原始 CSV 做字节级 SHA256，证明摄取层物理完整、未被篡改。
- 第二道闸门 `create_and_validate_view`：对 **10 个锁定视图**逐一回读校验（行数 / 列集 / 类型字面比对 / 唯一性 / 空值 / 值域），任一失败即断链。

### 2.2 十个锁定视图（口径版本锁定，可 diff、可复跑）

| # | 视图 | 粒度 | 行数 | 用途 |
|---|---|---|---|---|
| 1 | `yearly_valence` | 年 | 100 | 年度聚合基线 |
| 2 | `decade_features` | 十年 | 11 | 十年聚合（含残缺桶 2020s 标记） |
| 3 | `regression_data` | 艺人×年 | 58,236 | 面板回归数据 |
| 4 | `instrumental_vs_vocal` | 十年×类型 | 22 | 器乐/人声分岔 |
| 5 | `song_version_study` | 经典曲×十年 | 129 | 天然实验池（未清洗） |
| 6 | `acoustic_trajectory` | 十年 | 11 | 原声度轨迹 + 四分位 |
| 7 | `era_quadrant` | 十年 | 11 | **原声↔能量 二维象限**（看板主数据源） |
| 8 | `sixties_subgenres` | 1960s 子群 | 3 | 1960s 三子群画像（下钻） |
| 9 | `track_type_dispersion` | 十年×类型 | 22 | 分布形状（IQR + 三段占比） |
| 10 | `song_version_study_clean` | 清洗后经典曲×十年 | **81** | 小多图 + Silent Night 深潜（看板 Phase 3 数据底座） |

> 口径锁定于 2026-09-26 ~ 2026-09-29，依据对真实数据库的**探测**（而非理论推导），全部落在
> `release/verify/skill_refs/references/locked_views.py`，由 `lv10.py` 逐视图复验。

### 2.3 数据清洗铁证（剔除项，已在视图层固化）

- **剔除 5 首污染曲目**（泛用名 / 同题异曲，击穿「同一首作品」前提）：
  `overture`、`summertime`、`i love you`、`joy to the world`、`ave maria`。
  清洗链路：647 行 / 15 首 → 剔除 5 首 → **457 行 / 10 首**。
- **剔除 16 条物理不可能年份记录**（录音年早于作品创作年，如《The Christmas Song》标 1932 实为 1944）：
  457 → 445 行（创作年硬约束）。
- **剔除 9 组同录音重发重复**（跨十年复现）：445 → **436 行**，最终聚合为 **81 格 / 10 首 / 9 个十年**。
- 全部落在 1932–1949，**1950 年后零违例**——证明约束精准、无错杀。

### 2.4 前端零硬编码（核心诚信承诺）

看板里出现的**每一个数字**（`SVC_SONGS` 81 格、`SVC_POOLED` 9 十年、`EQ_ROWS` 11 十年、
`EQ_SEG` 10 段、`SLN_RECORDS` 44 条 Silent Night 明细）都来自上述 DuckDB 视图的**实查值**，
经 `check3.py` / `check4.py` **逐值回读比对**（81 格 × 9 字段 + 池化 + 44 条）。

前端不含任何凭空写死的统计结论——这就是「法医级」的含义：**可复算、可对账、可证伪**。

---

## 三、核心统计发现

### 3.1 世纪声学漂移（已被机器逐值确认）
- **原声度（acousticness）百年轨迹**：1920s **0.802** → 2020s **0.220**，单调下滑。
- **1940s 是全局峰值 0.871**（恰好落在 IQR 带外，因极强左偏）；**2020s 谷底 0.220**。
- **1960s → 1970s 是「断层带」**：低原声高能量占比从 19.2% 跳到 45.2%（+25.9pp），
  占全世纪位移的 **53.8%**，是「先趴 30 年，一跤跌倒，笔直滑走」轨迹的拐点。
- **原声 ↔ 能量 相关性**：PC1 解释率 **99.54%**；十年均值点间相关 **r = −0.988529**（近乎完美负相关）；
  在 2000s 达到峰值 −0.7485，2020s 回落至 −0.5000（随样本量骤减，须并列陈述，不得单独归因）。

### 3.2 ICC 修正（旧口径被证伪）
- 旧叙事口径给出的内部一致性为 **0.88 / 0.49**；经「ICC(1,1)」修正后实为 **0.64 / 0.17**。
- 修正说明已写进看板文案与断言（`check3.py` 文案核对项含 `ICC(1,1)`、`0.88 / 0.49` 溯源锚点），
  确保结论与呈现**永不漂移**。

### 3.3 原点扰动证伪四象限（叙事稳健性检验）
- 对「象限阈值 0.5/0.5」「1960s 是否双簇」「2020s 回落是否风格信号」等核心叙事，
  做了**阈值扰动（5 组）与原点扰动**对照：
  - 换阈值 0.4/0.6 或 0.6/0.4，低原声高能量占比漂移最大仅 ±12.5pp，但**质心稳定、边界敏感**
    —— 证明「三分结构」是真实谱，不是切分伪影。
  - 2020s 器乐仅 28 首、95% CI 完全覆盖 2010s 点值 → **不得用于任何趋势解读**（前端已做三层视觉降级）。
  - 「1960s 双峰」被证伪：实际是**负峰度扁平平台**（skew −0.6775、kurtosis −0.7182），
    叙事已改为「过渡期拉得最宽」。
- 这些「证伪实验」本身即构成看板的方法论诚信声明：**结论经得起把定义推到边界**。

---

## 四、如何验证（一键复跑 8 层自动化测试）

验证体系**完全自包含**：首次运行会从 `data/archive/data.csv` 重建 `spotify.duckdb`，
不需要原工作区任何其他文件。

### 4.1 准备数据

原始数据集**不随仓库分发**（约 28 MB），请自行下载后放到 `data/archive/data.csv`：

- 数据集：**Spotify Dataset 1921-2020, 160k+ Tracks**（作者 Yamac Eren Ay）
- 来源：<https://www.kaggle.com/datasets/yamaerenay/spotify-dataset-1921-2020-160k-tracks>
- 许可：Community Data License Agreement – Sharing, Version 1.0

```bash
mkdir -p data/archive
# 把下载到的 data.csv 放到 data/archive/data.csv
```

### 4.2 环境依赖

| 依赖 | 说明 |
|---|---|
| Python 3.13 | 需要 `duckdb`（`pip install duckdb`） |
| Node.js | 仅用于 `node --check` 校验内联 JS 语法（可用环境变量 `WB_NODE` 覆盖） |
| Microsoft Edge | Headless 模式；可用环境变量 `WB_EDGE` 覆盖，否则自动探测默认安装位 |

### 4.3 一键运行

```bash
# Windows
.venv/Scripts/python.exe release/verify/run_all.py

# macOS / Linux
.venv/bin/python release/verify/run_all.py
```

- 想**保留运行期 DOM 探针 / 截图**以便排查，加 `--keep`：
  ```bash
  python release/verify/run_all.py --keep
  ```

### 4.4 八层测试职责（对应 8 个脚本）

| 层 | 脚本 | 验证什么 |
|---|---|---|
| L1 数据 | `lv10.py` | 10/10 锁定视图全部 VALID（行数/列/类型/唯一/空值/值域） |
| L2a 源码 | `check3.py` | 内联 JS 语法 + SVC 数据块逐值比对 + 文案数字 + 结构 + 反模式守卫 |
| L2b 源码 | `check4.py` | EQ_ROWS/EQ_SEG 逐值比对 + 原点网格/段派生量重算 + 文案 + 结构 + 反模式 |
| L3a 渲染 | `render_check.py` | Headless Edge 三宽度（1440/900/478）渲染：计数 + 几何 + Hover + 注解零重叠 |
| L3b 渲染 | `render_check4.py` | 三宽度 × 八断言：线宽速度编码 / 椭圆不越界 / X 轴反向 / 三段式色块呼应 |
| L4a 交互 | `probe4.py` | 真实 `mouseenter` → 1960s tooltip 必须含两侧断层距离 |
| L4b 交互 | `probe5.py` | 目录滚动高亮 / 进度条 / 点击跳转 / 锚点落地（scroll-spy 逻辑探针） |
| L5 离线 | `offline5.py` | 断网对照：CDN 版退化、离线版 5 图全渲染（机器证明「离线可用」） |

> 退出码 0 = 8/8 全绿。任何一层失败都会在汇总里标 `FAIL` 并给出退出码，便于定位。
>
> **稳定性设计**：两层无头浏览器脚本都内置「就绪门」——先轮询到看板主脚本初始化完成
> （如 `#toc` 五个章节锚点就位）才开始探测，而不是靠死等若干毫秒；
> `run_all.py` 还会在每轮开始前回收残留的无头 Edge 进程、并给 2 秒让系统释放 GPU / 共享内存，
> 另对任一层返回非 0 自动重试（最多 3 次）。
> 这样即便在低配机器上串行跑 7 轮无头渲染，也不会因资源累积污染结果。

---

## 五、仓库结构

```
.
├── README.md                       ← 本文件
├── d3_dashboard.offline.html       ← 最终看板（完全离线单文件 ≈491KB，零外部请求）★
├── d3_dashboard.html               ← 最终看板（CDN 依赖版，开发/对照用）
├── spotify_narrative_report.html   ← 数据叙事报告页
├── 1960s_三子群二维质心与离散度.html ← 下钻分析页
├── 8视图数据接口清单.html            ← 视图口径与字段说明
├── Task_B_四视图证据金字塔.html      ← 证据层级说明
├── Phase4_探查报告.md               ← 数据探查过程记录
├── Phase5_交付清单.md               ← 交付验收清单
├── handover_package.md             ← 交接文档
├── pipeline.py / pipeline_test.py   ← 数据管道与自测
├── step1_profile.py                ← 数据画像
├── db_schema.sql                   ← 数据库 schema
├── evidence/                       ← 证据材料（截图 + 校验结果 CSV）
└── release/
    ├── README.md                   ← 交付包说明（含完整口径台账）
    ├── skills/                     ← 沉淀的两个方法论 Skill
    │   ├── trend-falsification-check.md      ← 趋势/叙事可证伪检验方法论
    │   └── d3-single-file-dashboard.md       ← 多区块长页 + 离线单文件打包方法论
    └── verify/                     ← 8 层自动化验证体系（完全自包含）
        ├── paths.py                ← 统一路径自定位（绝不写死绝对路径）
        ├── build_db.py             ← 0 层：从 data.csv 重建 spotify.duckdb
        ├── make_p4_export.py       ← 生成台账真值 p4_export.json
        ├── run_all.py              ← 一键编排：建库 → 导出 → 跑 8 层 → 汇总 → 清理
        ├── lv10.py / check3.py / check4.py
        ├── render_check.py / render_check4.py
        ├── probe4.py / probe5.py / offline5.py
        └── skill_refs/             ← 验证体系依赖的锁定口径（可复算台账）
            ├── references/locked_views.py
            └── scripts/create_and_validate_view.py
```

**未入库内容**（见 `.gitignore`）：

- `data/`、`archive/`、`release/data/` —— 原始数据集（约 28 MB），获取方式见 §4.1
- `verify/`（项目根目录下）—— Headless 浏览器运行期产物，体积近 300 MB 且含本机浏览器配置
- `.venv/`、`__pycache__/`、`_retired_work*/` —— 运行环境与开发期过程归档

> ⚠️ 注意：根目录的 `verify/`（运行期临时产物，已忽略）与 `release/verify/`（8 层测试源码，**已入库**）
> 是两个不同的东西，`.gitignore` 用 `/verify/` 前缀斜杠精确区分。

---

## 六、方法论沉淀

这个项目产出了两个可复用的方法论 Skill（见 `release/skills/`）：

| Skill | 解决什么问题 |
|---|---|
| `trend-falsification-check` | 在把「数据趋势」写进报告之前，用可证伪的检验拆一遍——判断它是真信号，还是抽样偏差 / 技术史混淆 / 构成变化制造的假象 |
| `d3-single-file-dashboard` | 构建单文件 HTML 的 D3 交互式看板（尤其 CDN 慢 / 被墙的离线场景），以及无法人工看浏览器时用 headless 自动验证图表真实渲染 |

---

## 七、复现保证（一句话收口）

> 在任意装有 Python 3.13(duckdb) + Edge 的机器上，放入数据集后只需一句
> `python release/verify/run_all.py`，即可从 `data/archive/data.csv`
> 重建数据库、复算全部 10 个视图、逐值回读看板的每一个数字、并用无头浏览器实跑交互与离线渲染——
> **8/8 全绿即代表「结论可复现、数据未被篡改、叙事经得起证伪」**。
