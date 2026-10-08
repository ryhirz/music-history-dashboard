# -*- coding: utf-8 -*-
"""create_and_validate_view —— 三个目标视图的**已锁定口径**（可执行台账）

这份文件是 SKILL.md《目标视图的参数预置表》的**可执行版本**。
SQL 与断言散落在文档里容易被抄错，落成代码则天然可校验、可 diff、可直接跑。

口径锁定于 2026-09-26，依据是对 `E:\\产品\\曲风数据分析\\spotify.duckdb`
的真实探测（不是理论推导）。事实来源：

    raw_tracks 视图 → archive/data.csv（170,653 行 × 19 列）
    year 范围 1921–2020，共 100 个不同取值，无空值、无重复键
    (artists, year) 组合数 = 58,236，两列均无空值

── 2026-09-26 命名统一 ────────────────────────────────────────────────
旧名 `yearly_aggregates` 与 `artist_panel` 已 DROP，统一采用与专家契约一致的
新名 `yearly_valence` 与 `regression_data`。三视图为：

    yearly_valence    100 行      按年聚合
    decade_features   11 行       按十年聚合
    regression_data   58,236 行   按 (artist, year) 聚合

⚠️⚠️ 2026-09-26 更正记录：推翻一次错误的「合并」判断 ⚠️⚠️
────────────────────────────────────────────────────────────────────
本文件曾一度把三视图改写为 `yearly_aggregates` / `decade_features` / `artist_panel`，
并给出论断：称 `yearly_valence` 与 `regression_data` 是**父子集关系**、
「`yr` 与 `n` 逐行全等」「`mean_valence` 仅差 ~1 ULP 噪声」，据此把两者合并。

**该论断经实测证伪，已撤销。** 实测反证（`spotify.duckdb`，2026-09-26）：

    yearly_valence   行数  100        GROUP BY 1     （按年）
    regression_data  行数  58,236     GROUP BY 1, 2  （按艺人-年）
    两视图按 yr 连接的行数           58,236   → 1 → 多 关系，不是父子集
    n vs n_tracks 不等的行数          58,236 / 58,236（全部不等）
    mean_valence 不等的行数           58,236 / 58,236，最大差 0.623

两视图行数相差 582 倍、聚合键不同、`n` 全不相等，**不构成任何形式的父子集**。
「逐行全等」与「~1 ULP」两条记述与实际数据完全相反。

**教训**：合并判断必须落在**实测**上，不能落在「列名看起来像子集」的直觉上。
`yearly_valence` 的列确实 ⊂ `regression_data` 的列，但**列包含关系不等于行/值一致**——
前者「每年一行」，后者「每艺人每年一行」，列名相同而粒度不同。
这类错误若未被拦下，会直接删掉分析师依赖的视图。

跑法（需要装了 duckdb 的解释器）：

    "E:\\产品\\曲风数据分析\\.venv\\Scripts\\python.exe" \\
        "C:\\Users\\Icarus\\.workbuddy\\skills\\create_and_validate_view\\references\\locked_views.py"

退出码 0 = 三个视图全部 VALID，1 = 有视图未通过。

⚠️ 调整分析窗口（例如改成 2005–2020）时，改的就是本文件里的 SQL 与断言，
   技能本体（scripts/create_and_validate_view.py）一行都不用动 ——
   这正是「SQL 外置为调用参数」这个设计的用意。

── 流水线编排契约（**不是**本技能的职责，由 Agent 调度层执行）────────────
本文件只管 D2（视图口径）。它**不校验**源文件 data.csv 有没有被篡改 ——
那是另一个技能 `data_fingerprint_check` 的职责（D1，文件层 SHA256）。

两个闸门**物理隔离、正交、不可互相替代**：

    D1  data_fingerprint_check  →  守 data.csv 的字节（摄取层物理完整性）
    D2  create_and_validate_view →  守视图的 SQL 口径（转换聚合层逻辑正确性）

正交性：文件没被篡改 ≠ SQL 没被改坏；SQL 正确 ≠ 文件没被换过。
两者没有因果包含关系，所以不能合并成一个技能，只能**串联**。

Agent 调度时的**强制前置依赖**：

    [D1: data.csv SHA256 == 期望值]  ──通过──▶  [D2: 三个视图全部 VALID]
              │                                        │
              └──失败──▶ 立即中止，不进入 D2            └──失败──▶ 断链，后续视图不建

**这个前置依赖已固化为可执行入口 —— 不要再手工依次跑两条命令：**

    "E:\\产品\\曲风数据分析\\.venv\\Scripts\\python.exe" \\
        "E:\\产品\\曲风数据分析\\pipeline.py" --expected-hash <64位sha256>

    # 只改了 SQL、确认数据文件未动时（显式逃生舱）：
    "...python.exe" "...\\pipeline.py" --skip-d1

`pipeline.py` 是纯编排薄壳（零校验逻辑、零 import 本技能），退出码语义：
    0 = 全链路安全 / 10 = D1 失败(已断链) / 20 = D2 失败(已断链) / 2 = 编排层错误
它的契约测试在 `E:\\产品\\曲风数据分析\\pipeline_test.py`（35 条断言，
含「D1 失败时用视图定义快照证明 D2 确实没碰库」）。

为什么是 Agent 调度、而不是技能互相调用：
  1. 变更面不同 —— 改 SQL 只需重跑 D2，不必重算 29.6 MB 的 SHA256；
  2. 错误可分 —— 「文件变了」与「行数不对」永不混在同一条堆栈里；
  3. 触发频率不同 —— D2 每视图触发一次，D1 一次交付只需一次。

本文件因此**不 import** `data_fingerprint_check`，也不调用它。详见 SKILL.md
《与 data_fingerprint_check 的分工》。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from create_and_validate_view import create_and_validate_view  # noqa: E402

# release 自定位：本文件在 release/verify/skill_refs/references/locked_views.py
#   .parent            = references
#   .parent.parent     = skill_refs
#   .parent.parent.parent      = verify
#   .parent.parent.parent.parent = release
# 指向 release/ 内由 build_db.py 从随包 data.csv 重建的 duckdb。
_RELEASE = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = str(_RELEASE / "data" / "spotify.duckdb")

# ══════════════════════════════════════════════════════════════════════
# 十个视图的锁定口径。顺序即执行顺序，不可乱序、不可并行。
#
# 前三个（yearly_valence / decade_features / regression_data）2026-09-26 锁定；
# 第四、五个（instrumental_vs_vocal / song_version_study）2026-09-27 新增；
# 第六个（acoustic_trajectory）2026-09-27 新增；
# 第七个（era_quadrant）2026-09-27 新增。**Task B 至此全部收官（四个视图）。**
# 第八个（sixties_subgenres）2026-09-28 新增。1960s 深潜，era_quadrant 的下钻补充。
# 第九个（track_type_dispersion）2026-09-29 新增。D3 看板 Phase 2 的数据底座，
#         instrumental_vs_vocal 的统计精度升级版（补 sd / 四分位 / 分布形状）。
# 第十个（song_version_study_clean）2026-09-29 新增。D3 看板 Phase 3 的数据底座，
#         song_version_study 的清洗版：剔泛用名污染 + 创作年硬约束 + 同录音去重。
# ══════════════════════════════════════════════════════════════════════

VIEWS: list[tuple[str, str, dict]] = [
    # ── 1. yearly_valence：年度愉悦度聚合，100 行 ────────────────────
    # ⚠️ 本视图**不是** regression_data 的子集：前者按年（每年一行），
    #    后者按艺人-年（每艺人每年一行），粒度不同、不可合并。
    #    详见文件头《更正记录》。
    (
        "yearly_valence",
        """CREATE OR REPLACE VIEW yearly_valence AS
SELECT year AS yr, avg(valence) AS mean_valence, count(*) AS n
FROM raw_tracks WHERE year IS NOT NULL GROUP BY 1 ORDER BY 1""",
        {
            "min_rows": 100,
            "max_rows": 100,
            "required_columns": [
                "yr",
                "mean_valence",
                "n",
            ],
            "column_types": {
                "yr": "BIGINT",
                "mean_valence": "DOUBLE",
                "n": "BIGINT",
            },
            "unique_columns": ["yr"],
            "null_check_columns": ["yr"],
            # value_bounds 只做单列值域合理性校验，不做跨视图等值比对 ——
            # 浮点聚合列有 ~1 ULP 非确定性，等值断言必然假阳性。
            "value_bounds": {
                "mean_valence": {"min": 0, "max": 1},
            },
        },
    ),
    # ── 2. decade_features：按十年聚合，11 行（1920s–2020s） ─────────
    # 注意 SQL 里用的是整数除法 `//` 而非 `/`：
    # DuckDB 的 `/` 是真除法，(1921/10)*10 = 1921.0，分组会退化成按年（100 行）。
    # 这个错误不会抛异常，只会静默给出错误的聚合粒度。
    #
    # is_partial_decade 标记 2020s 残缺桶（仅 1 年数据），是事实基座铁律
    # 「2020 器乐度断崖属抽样构成变化、必须单列」的数据支撑，不可删。
    (
        "decade_features",
        """CREATE OR REPLACE VIEW decade_features AS
SELECT year//10*10 AS decade,
       (year//10*10 = 2020) AS is_partial_decade,
       avg(danceability) AS mean_danceability,
       avg(energy) AS mean_energy,
       count(*) AS n
FROM raw_tracks WHERE year IS NOT NULL GROUP BY 1, 2 ORDER BY 1""",
        {
            "min_rows": 11,
            "max_rows": 11,
            "required_columns": [
                "decade",
                "is_partial_decade",
                "mean_danceability",
                "mean_energy",
                "n",
            ],
            "column_types": {
                "decade": "BIGINT",
                "is_partial_decade": "BOOLEAN",
                "mean_danceability": "DOUBLE",
                "mean_energy": "DOUBLE",
                "n": "BIGINT",
            },
            "unique_columns": ["decade"],
            "null_check_columns": ["decade", "is_partial_decade"],
            "value_bounds": {
                "mean_danceability": {"min": 0, "max": 1},
                "mean_energy": {"min": 0, "max": 1},
            },
        },
    ),
    # ── 3. regression_data：艺人 × 年面板，58,236 行（0% 容差） ───────
    # handover_package.md 中称为 artist_panel，同一段 SQL 的别名；
    # 用户 2026-09-26 决定统一采用 regression_data 这一新名。
    #
    # 行数断言用绝对相等：确定性管道不需要伪容差。
    # n_tracks 是整数计数，是确定性的；只要 raw_tracks 不变、SQL 无随机源，
    # COUNT(*) 必须恒等于 58236。差 1 行就意味着「底层数据被动了」或
    # 「GROUP BY 被改出了笛卡尔积」，两种都必须拦下 —— 容差会把它们一起放过去。
    (
        "regression_data",
        """CREATE OR REPLACE VIEW regression_data AS
SELECT artists AS artist, year AS yr, avg(valence) AS mean_valence,
       avg(energy) AS mean_energy, count(*) AS n_tracks
FROM raw_tracks WHERE year IS NOT NULL AND artists IS NOT NULL
GROUP BY 1, 2""",
        {
            "min_rows": 58236,
            "max_rows": 58236,
            "required_columns": [
                "artist",
                "yr",
                "mean_valence",
                "mean_energy",
                "n_tracks",
            ],
            "column_types": {
                "artist": "VARCHAR",
                "yr": "BIGINT",
                "mean_valence": "DOUBLE",
                "mean_energy": "DOUBLE",
                "n_tracks": "BIGINT",
            },
            "unique_columns": ["artist", "yr"],
            "null_check_columns": ["artist", "yr"],
            "value_bounds": {
                "mean_valence": {"min": 0, "max": 1},
                "mean_energy": {"min": 0, "max": 1},
            },
        },
    ),
    # ── 4. instrumental_vs_vocal：器乐/人声 × 十年交叉，22 行 ────────
    # 2026-09-27 新增（Task B 首个视图）。支撑报告 §2.2「器乐/人声分岔双线图」。
    #
    # 粒度 = (decade, track_type)，11 个十年 × 2 种类型 = 22 行，无缺桶。
    #   track_type: instrumentalness >= 0.5 → 'instrumental'，否则 → 'vocal'
    #
    # 同样注意 `//` 而非 `/`（真除法会让分组退化成按年，行数变 100）。
    # is_partial_decade 标记 2020s 两支，供前端做视觉降权，不可删。
    #
    # 额外两个聚合列 mean_instrumentalness / mean_energy / mean_valence：
    #   - mean_instrumentalness 让分组阈值本身可审计
    #     （器乐组实测 0.787–0.849，人声组 0.005–0.061，分界干净）
    #   - mean_energy / mean_valence 为后续 era_quadrant 视图预留接口
    #
    # 校验口径核对（2026-09-27 实测，用于确认视图忠实反映底层数据）：
    #   1920s 器乐 0.9726 / 人声 0.6838   ← 报告 §2.2 图注 0.973 / 0.684
    #   1970s 器乐 0.4729                  ← 报告 §2.2 图注 0.473（触底平台期）
    #   2020s 人声 0.2162                  ← 报告 §2.2 图注 0.215
    (
        "instrumental_vs_vocal",
        """CREATE OR REPLACE VIEW instrumental_vs_vocal AS
SELECT year // 10 * 10 AS decade,
       CASE WHEN instrumentalness >= 0.5 THEN 'instrumental' ELSE 'vocal' END AS track_type,
       (year // 10 * 10 = 2020) AS is_partial_decade,
       avg(acousticness) AS mean_acousticness,
       avg(instrumentalness) AS mean_instrumentalness,
       avg(energy) AS mean_energy,
       avg(valence) AS mean_valence,
       count(*) AS n
FROM raw_tracks
WHERE year IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2""",
        {
            "min_rows": 22,
            "max_rows": 22,
            "required_columns": [
                "decade",
                "track_type",
                "is_partial_decade",
                "mean_acousticness",
                "mean_instrumentalness",
                "mean_energy",
                "mean_valence",
                "n",
            ],
            "column_types": {
                "decade": "BIGINT",
                "track_type": "VARCHAR",
                "is_partial_decade": "BOOLEAN",
                "mean_acousticness": "DOUBLE",
                "mean_instrumentalness": "DOUBLE",
                "mean_energy": "DOUBLE",
                "mean_valence": "DOUBLE",
                "n": "BIGINT",
            },
            # (decade, track_type) 二维键唯一 —— 两个都是确定性列
            # （BIGINT 与 VARCHAR），不是浮点聚合列，可安全用于等值断言。
            "unique_columns": ["decade", "track_type"],
            "null_check_columns": [
                "decade",
                "track_type",
                "is_partial_decade",
                "mean_acousticness",
                "n",
            ],
            # value_bounds 只做单列值域合理性校验，不做跨视图等值比对。
            "value_bounds": {
                "mean_acousticness": {"min": 0, "max": 1},
                "mean_instrumentalness": {"min": 0, "max": 1},
                "mean_energy": {"min": 0, "max": 1},
                "mean_valence": {"min": 0, "max": 1},
            },
        },
    ),
    # ── 5. song_version_study：经典曲目 × 十年，129 行 ───────────────
    # 2026-09-27 新增（Task B 第二个视图）。支撑报告 §3.4「天然实验」——
    # Silent Night / Summertime 的跨年代版本对比，证明原声度捕捉的是
    # 编曲/乐器选择，而非录音年代。
    #
    # 粒度 = (song_key, decade)，song_key = lower(trim(name)) 归一化曲名。
    # 129 行 = 15 首经典曲目 × 各自覆盖的 8–9 个十年。
    #
    # ⚠️ 筛选门槛的核心是 `n_decades_multi >= 7`（有 >=2 个版本的十年数）。
    #    为什么不用 distinct_artists 判「真 IP」：实测两者无法区分 ——
    #      silent night  v=45 decades=8 distinct_artists=40   ← 真翻唱传统
    #      home          v=41 decades=9 distinct_artists=39   ← 泛用名（不同歌同名）
    #    「home / goodbye / intro / i love you」这类泛用短名是几十首不同的歌
    #    恰好同名，不是同一首歌被反复翻录。若不过滤会污染天然实验
    #    「对象固定、只变时间」的前提。
    #    n_decades_multi 是实测中唯一划出干净分界的信号：
    #      真 IP 落在 7–9，泛用名落在 4–6，中间无重叠。
    #
    # 三层筛选：
    #   1) n_decades >= 8        覆盖至少 8 个十年
    #   2) n_decades_multi >= 7  至少 7 个十年里有 >=2 个版本（真 IP 判别）
    #   3) n_versions_total >= 25 总版本数足够
    #   4) first_year <= 1949 AND last_year >= 2010
    #      —— 强制覆盖报告锚点所需的 1940s↔2010s 跨度
    #
    # 由 skill 的精确匹配口径延续：报告 §3.4 必须用 lower(trim(name)) 精确相等，
    # 不可用 ILIKE '%silent night%'（会捞到 Silent Night Medley 等衍生标题，
    # 导致 1950s=21 版而非正确的 10 版）。本视图沿用同一归一化键。
    #
    # 锚点核对（实查）：
    #   silent night  1940s n=3 acoustic=0.9787  |  2010s n=5 acoustic=0.9536
    #                 ← 报告 §3.4 的 0.979 / 0.954
    #   summertime    1930s n=9 acoustic=0.7732  |  2010s n=3 acoustic=0.0971
    #                 ← 报告 §2.2 的 0.773 / 0.097
    #
    # ⚠️ n_versions_total 的类型是 HUGEINT 而非 BIGINT：
    #    DuckDB 对 BIGINT 的 sum() 会溢出提升为 HUGEINT。严格字面比对下
    #    写 BIGINT 必然误报 TYPE_MISMATCH。此类型由 DESCRIBE 实查得到。
    #
    # ⚠️ is_partial_decade 本视图全部为 False（候选池跨度到 2010s，2020s 桶为空）。
    #    字段仍按契约保留：粒度含 decade 维度，契约要求标记残缺十年。
    (
        "song_version_study",
        """CREATE OR REPLACE VIEW song_version_study AS
WITH per_decade AS (
    SELECT lower(trim(name)) AS song_key,
           year // 10 * 10   AS decade,
           count(*)          AS n_versions,
           avg(acousticness)     AS mean_acousticness,
           avg(instrumentalness) AS mean_instrumentalness,
           avg(energy)           AS mean_energy,
           avg(valence)          AS mean_valence,
           min(year) AS year_min,
           max(year) AS year_max
    FROM raw_tracks
    WHERE year IS NOT NULL AND name IS NOT NULL
    GROUP BY 1, 2
),
song_stats AS (
    SELECT song_key,
           count(*)                                AS n_decades,
           count(*) FILTER (WHERE n_versions >= 2) AS n_decades_multi,
           sum(n_versions)                         AS n_versions_total,
           min(year_min)                           AS first_year,
           max(year_max)                           AS last_year
    FROM per_decade
    GROUP BY 1
)
SELECT p.song_key,
       p.decade,
       (p.decade = 2020) AS is_partial_decade,
       p.year_min,
       p.year_max,
       p.n_versions,
       p.mean_acousticness,
       p.mean_instrumentalness,
       p.mean_energy,
       p.mean_valence,
       s.n_decades,
       s.n_decades_multi,
       s.n_versions_total,
       s.last_year - s.first_year AS year_span
FROM per_decade p
JOIN song_stats s USING (song_key)
WHERE s.n_decades       >= 8
  AND s.n_decades_multi >= 7
  AND s.n_versions_total >= 25
  AND s.first_year <= 1949
  AND s.last_year  >= 2010
ORDER BY p.song_key, p.decade""",
        {
            # 精确值：129（Task B 执行时实测，已从设计阶段的 110–135 宽区间收紧）
            "min_rows": 129,
            "max_rows": 129,
            "required_columns": [
                "song_key",
                "decade",
                "is_partial_decade",
                "year_min",
                "year_max",
                "n_versions",
                "mean_acousticness",
                "mean_instrumentalness",
                "mean_energy",
                "mean_valence",
                "n_decades",
                "n_decades_multi",
                "n_versions_total",
                "year_span",
            ],
            "column_types": {
                "song_key": "VARCHAR",
                "decade": "BIGINT",
                "is_partial_decade": "BOOLEAN",
                "year_min": "BIGINT",
                "year_max": "BIGINT",
                "n_versions": "BIGINT",
                "mean_acousticness": "DOUBLE",
                "mean_instrumentalness": "DOUBLE",
                "mean_energy": "DOUBLE",
                "mean_valence": "DOUBLE",
                "n_decades": "BIGINT",
                "n_decades_multi": "BIGINT",
                # ⚠️ HUGEINT（sum(BIGINT) 的溢出提升），不是 BIGINT
                "n_versions_total": "HUGEINT",
                "year_span": "BIGINT",
            },
            # (song_key, decade) 二维键唯一 —— 均为确定性列（VARCHAR + BIGINT）
            "unique_columns": ["song_key", "decade"],
            "null_check_columns": [
                "song_key",
                "decade",
                "is_partial_decade",
                "n_versions",
                "mean_acousticness",
            ],
            # value_bounds 只做单列值域合理性校验，不做跨视图等值比对。
            "value_bounds": {
                "mean_acousticness": {"min": 0, "max": 1},
                "mean_instrumentalness": {"min": 0, "max": 1},
                "mean_energy": {"min": 0, "max": 1},
                "mean_valence": {"min": 0, "max": 1},
                "n_decades": {"min": 8, "max": 11},
                "n_decades_multi": {"min": 7, "max": 11},
                "n_versions_total": {"min": 25, "max": 200},
                "year_span": {"min": 60, "max": 100},
            },
        },
    ),
    # ── 6. acoustic_trajectory：原声度年代轨迹，11 行（1920s–2020s）──────
    # 2026-09-27 新增（Task B 第三个视图）。支撑报告中贯穿始终的
    # 「原声度随年代变化的整体轨迹」，未来 D3 交互折线图的核心数据源。
    # 把散在 §2.1 / §2.2 / §3.4 的年代趋势整合为一条可复算的时间序列。
    #
    # 粒度 = (decade)，纯时间维度，11 行。
    #
    # ⚠️ 为什么同时给 sd 与三个四分位（而非只给均值线）：
    #    分布随年代剧烈变形 —— 1920s 是「70% 挤在 0.9-1.0」的强左偏，
    #    2020s 是「62% 挤在 0.0-0.2」的右偏。只画均值会丢掉这个形态变化。
    #
    # ⚠️ 关键实测事实：1940s 的 mean=0.8710 落在 IQR [0.8800, 0.9910] **之外** ——
    #    11 个十年里唯一一个。这不是数据错误，是极度左偏的自然结果
    #    （72% 样本挤在 0.9-1.0 把 p25 推到 0.880 之上，左尾 4.6% 低值把均值拽到 0.871）。
    #    因此下游若只画「均值线 + IQR 带」，1940s 的点会飘在色带外。
    #    **必须同时用 sd 提供对称误差带**（mean±1sd = [0.644, 1.098] 能包住均值）。
    #
    # ⚠️ stddev() 在 DuckDB 中就是样本标准差（ddof=1），与 stddev_samp() 输出完全相同。
    #    实测 1920s 两者均为 0.3204。
    #
    # ⚠️ 用 quantile_cont（连续分位数）而非 quantile_disc：
    #    连续分位数对偶数样本量更稳健，是标准选择。口径已固定。
    #
    # 类型实查（吸取 sum→HUGEINT 教训）：stddev / quantile_cont 均返回 DOUBLE，
    # 不涉及整数求和，无溢出提升风险。
    #
    # 两个「一次性验证」（不写进 validate_rules —— 七键无法表达列间不等式/等式）：
    #   1) p25 <= median <= p75 单调性：实测 11/11 成立
    #   2) median 列 == 另算的 quantile_cont(acousticness,0.50)：实测 11/11 相等
    # 不塞进七键的理由：技能的设计原则是「每个键只管一件事」，
    # 跨列约束会破坏该契约；改为执行后一次性验证并记录。
    #
    # 轨迹锚点（实查，与报告 §2.1 吻合）：
    #   1920s mean=0.8016 → 2020s mean=0.2199（报告称 0.802 → 0.220）
    #   1960s mean=0.6240（介于 1950s 0.8403 与 1970s 0.4002 之间的中期转折）
    #   sd 呈「U 形」：1920s 0.3204 → 1950s 0.1867（谷底）→ 1990s 0.3165 → 2020s 0.2405
    (
        "acoustic_trajectory",
        """CREATE OR REPLACE VIEW acoustic_trajectory AS
SELECT year // 10 * 10                   AS decade,
       (year // 10 * 10 = 2020)          AS is_partial_decade,
       avg(acousticness)                 AS mean_acousticness,
       stddev(acousticness)              AS sd_acousticness,
       quantile_cont(acousticness, 0.25) AS p25_acousticness,
       quantile_cont(acousticness, 0.50) AS median_acousticness,
       quantile_cont(acousticness, 0.75) AS p75_acousticness,
       count(*)                          AS n
FROM raw_tracks
WHERE year IS NOT NULL
GROUP BY 1, 2
ORDER BY 1""",
        {
            "min_rows": 11,
            "max_rows": 11,
            "required_columns": [
                "decade",
                "is_partial_decade",
                "mean_acousticness",
                "sd_acousticness",
                "p25_acousticness",
                "median_acousticness",
                "p75_acousticness",
                "n",
            ],
            "column_types": {
                "decade": "BIGINT",
                "is_partial_decade": "BOOLEAN",
                "mean_acousticness": "DOUBLE",
                "sd_acousticness": "DOUBLE",
                "p25_acousticness": "DOUBLE",
                "median_acousticness": "DOUBLE",
                "p75_acousticness": "DOUBLE",
                "n": "BIGINT",
            },
            "unique_columns": ["decade"],
            "null_check_columns": [
                "decade",
                "is_partial_decade",
                "mean_acousticness",
                "sd_acousticness",
                "p25_acousticness",
                "median_acousticness",
                "p75_acousticness",
                "n",
            ],
            "value_bounds": {
                "mean_acousticness": {"min": 0, "max": 1},
                "sd_acousticness": {"min": 0, "max": 1},
                "p25_acousticness": {"min": 0, "max": 1},
                "median_acousticness": {"min": 0, "max": 1},
                "p75_acousticness": {"min": 0, "max": 1},
                # 下界 2000 是因为 2020s 只剩 2,030 行（残缺十年）
                "n": {"min": 2000, "max": 20000},
            },
        },
    ),
    # ── 7. era_quadrant：年代 × (原声度, 能量) 二维象限，11 行 ──────────
    # 2026-09-27 新增（Task B 第四个视图，收官）。支撑报告 §3 的
    # 「原声 ↔ 能量」二元关系随年代的漂移，D3 层置信椭圆 / 2D 箱线图的数据底座。
    # 粒度 = (decade)，纯时间维度，11 行（1920s–2020s）。
    #
    # ── 三条附加约束（2026-09-27 用户批准，必须保留）──────────────────
    #
    # 【约束 1】象限阈值锁死常量 0.5 / 0.5，禁止改为「按年代自适应分位」。
    #    敏感性实测：换 ac>=0.6/en>=0.4 时 1960s 的「高原低能」占比从 54.7%
    #    变到 42.2%（漂 12.5pp）；换 ac>=0.4/en>=0.6 时变到 65.9%（漂 11.2pp）。
    #    若改用各年代自身的分位数分桶，每个年代的象限占比会被强行拉平，
    #    而「低原声高能」从 1.3% 涨到 75.9% 这个核心年代差异会被彻底抹掉。
    #    → 固定绝对阈值是让 11 个十年可比的前提，不可调。
    #
    # 【约束 2】1960s 是「最宽的单峰过渡带」，不是「双簇分离」。
    #    ⚠️ 这条必须写进注释，防止下游 D3 误用双峰框架解释。
    #    决定性证据（偏度 / 峰度，实测全 11 个十年）：
    #      · 1960s skew = -0.6775、kurtosis = -0.7182 —— 全表唯一偏度近 0
    #        且**峰度为负**的年代。双峰分布必然伴随**正峰度**（双峰比单峰更尖），
    #        负峰度恰恰是「扁平台型、非尖峰、非双峰」的数学特征。
    #      · 对照：1950s skew=-1.909/kurt=+3.856（单峰右偏）；
    #              1970s skew=+0.302/kurt=-1.233（单峰左偏）。
    #    直方图佐证：1960s 的 acousticness 20 桶从 0.00 到 0.95 逐级单调爬升，
    #      **无任何局部谷底**；12/20 个桶的占比都落在 14%-18% 的扁平带内。
    #    二维佐证：分到 (ac, en) 二维后三个子群在响度上单调拉开
    #      （声学低能 -14.98 dB → 混合 -10.63 dB → 非声学高能 -8.89 dB），
    #      说明该年代确有「安静民谣/爵士」与「响亮摇滚」的制作风格并列，
    #      但在 acousticness 单维上被 5,095 首混合曲平滑掉了，未形成断层。
    #    → 结论：叙事应表述为「过渡期拉得最宽」，不可表述为「两个簇」。
    #
    # 【约束 3】2020s 的 corr_ac_en 回落（-0.500）必须与样本量骤减并列陈述，
    #    不得单独归因于风格变化。2020s 本桶仅 2,030 行（is_partial_decade=true），
    #    相关系数在 2000s 达到峰值 -0.7485 后回落至 -0.5000，
    #    这个回落至少部分来自抽样构成变化，而非纯粹的听感趋势。
    #
    # ─────────────────────────────────────────────────────────────────
    #
    # 核心新指标 corr_ac_en 的单峰轨迹（实查）：
    #   1920s -0.1656 → 1940s -0.1576（最弱）→ 1950s -0.4640（陡增）
    #   → 2000s -0.7485（峰值）→ 2020s -0.5000（回落）
    #   即「原声↔能量」从近乎独立，渐绑成强反相关，又在流媒体时代重新解绑。
    #
    # 象限定义（ac=acousticness, en=energy，阈值均取 0.5）：
    #   pct_hiac_loen = ac>=0.5 且 en<0.5   （高原声低能量：老派声学）
    #   pct_hiac_hien = ac>=0.5 且 en>=0.5  （高原声高能量：混合过渡）
    #   pct_loac_loen = ac<0.5  且 en<0.5   （低原声低能量：清冷电子）
    #   pct_loac_hien = ac<0.5  且 en>=0.5  （低原声高能量：现代电子化）
    # 「低原声高能量」占比从 1920s 1.31% 单调涨到 2020s 75.86%，
    # **唯一一次大幅跃迁在 1960s→1970s（19.23% → 45.16%，+25.9pp）**，
    # 与报告 §2.2「以 1960s 中期为界分两段」完全咬合。
    #
    # ⚠️ 类型陷阱（已避）：sum(CASE...) 返回 HUGEINT（BIGINT 溢出提升，
    #    与 song_version_study 的 n_versions_total 同源）。本视图**不暴露裸 sum 列**，
    #    四列象限数据全部用 round(sum(...)*100.0/count(*), 2) 包成 DOUBLE 百分比，
    #    既规避 HUGEINT 断言的脆弱点，也让视图对下游图表直接可用。类型经 DESCRIBE 实查。
    #
    # value_bounds 依据：corr_ac_en 上界取 0 有数据支撑 ——
    #    11/11 个十年均为负相关，实测最大值为 -0.1576（1940s）。
    (
        "era_quadrant",
        """CREATE OR REPLACE VIEW era_quadrant AS
SELECT year // 10 * 10                   AS decade,
       (year // 10 * 10 = 2020)          AS is_partial_decade,
       avg(acousticness)                 AS mean_acousticness,
       stddev(acousticness)              AS sd_acousticness,
       avg(energy)                       AS mean_energy,
       stddev(energy)                    AS sd_energy,
       corr(acousticness, energy)        AS corr_ac_en,
       round(sum(CASE WHEN acousticness >= 0.5 AND energy <  0.5 THEN 1 ELSE 0 END)
             * 100.0 / count(*), 2)      AS pct_hiac_loen,
       round(sum(CASE WHEN acousticness >= 0.5 AND energy >= 0.5 THEN 1 ELSE 0 END)
             * 100.0 / count(*), 2)      AS pct_hiac_hien,
       round(sum(CASE WHEN acousticness <  0.5 AND energy <  0.5 THEN 1 ELSE 0 END)
             * 100.0 / count(*), 2)      AS pct_loac_loen,
       round(sum(CASE WHEN acousticness <  0.5 AND energy >= 0.5 THEN 1 ELSE 0 END)
             * 100.0 / count(*), 2)      AS pct_loac_hien,
       count(*)                          AS n
FROM raw_tracks
WHERE year IS NOT NULL
GROUP BY 1, 2
ORDER BY 1""",
        {
            "min_rows": 11,
            "max_rows": 11,
            "required_columns": [
                "decade",
                "is_partial_decade",
                "mean_acousticness",
                "sd_acousticness",
                "mean_energy",
                "sd_energy",
                "corr_ac_en",
                "pct_hiac_loen",
                "pct_hiac_hien",
                "pct_loac_loen",
                "pct_loac_hien",
                "n",
            ],
            "column_types": {
                "decade": "BIGINT",
                "is_partial_decade": "BOOLEAN",
                "mean_acousticness": "DOUBLE",
                "sd_acousticness": "DOUBLE",
                "mean_energy": "DOUBLE",
                "sd_energy": "DOUBLE",
                "corr_ac_en": "DOUBLE",
                # 四列象限数据经 round(...*100.0/count(*), 2) 包成 DOUBLE，
                # 规避裸 sum() 的 HUGEINT 溢出提升。类型经 DESCRIBE 实查。
                "pct_hiac_loen": "DOUBLE",
                "pct_hiac_hien": "DOUBLE",
                "pct_loac_loen": "DOUBLE",
                "pct_loac_hien": "DOUBLE",
                "n": "BIGINT",
            },
            "unique_columns": ["decade"],
            "null_check_columns": [
                "decade",
                "mean_acousticness",
                "sd_acousticness",
                "mean_energy",
                "sd_energy",
                "corr_ac_en",
                "pct_hiac_loen",
                "pct_hiac_hien",
                "pct_loac_loen",
                "pct_loac_hien",
                "n",
            ],
            "value_bounds": {
                "mean_acousticness": {"min": 0, "max": 1},
                "sd_acousticness": {"min": 0, "max": 0.5},
                "mean_energy": {"min": 0, "max": 1},
                "sd_energy": {"min": 0, "max": 0.5},
                # 上界 0 有数据支撑：11/11 个十年均为负相关，
                # 实测最大值 -0.1576（1940s）、最小值 -0.7485（2000s）
                "corr_ac_en": {"min": -1, "max": 0},
                "pct_hiac_loen": {"min": 0, "max": 100},
                "pct_hiac_hien": {"min": 0, "max": 100},
                "pct_loac_loen": {"min": 0, "max": 100},
                "pct_loac_hien": {"min": 0, "max": 100},
                # 下界 1 是保守值（2020s 仅 2,030 行）；上界 25000 覆盖单十年最大 20,000
                "n": {"min": 1, "max": 25000},
            },
        },
    ),
    # ── 8. sixties_subgenres：1960s 三子群制作风格画像，3 行 ─────────────
    # 2026-09-28 新增（1960s 深潜）。era_quadrant 的**下钻补充**，不是替代：
    #   era_quadrant 回答「1960s 整体是什么形态」（负峰度扁平平台），
    #   本视图回答「这个形态由什么构成」（三个可命名的制作风格簇）。
    #
    # 粒度 = (subgenre_label)，**仅含 1960s**，3 行。无 decade 列（只有一个年代）。
    #
    # ── 三条附加约束（2026-09-28 用户批准，必须保留）──────────────────
    #
    # 【约束 1】禁止用 acousticness / energy 的 η² 作为子群区分度的证据。
    #    ⚠️ 这是本视图最容易犯的错误，且极难自查。
    #    η² 排序前两名正是 acousticness (0.6556) 与 energy (0.6133) ——
    #    但它们**正是划分子群的定义变量**，其高 η² 属**循环论证**：
    #    用 ac/en 切出三组，再问「ac/en 能否区分这三组」，答案必然是能。
    #    若拿 η²>0.6 去宣称「子群区分度极强」，就是自证式结论。
    #    子群有效性的**独立证据只能来自非定义变量**：
    #      loudness  η²=0.2843  Cohen's d: A→B 1.038 / B→C 0.564 / A→C 1.585
    #      valence   η²=0.2096  Cohen's d: A→B 0.919 / B→C 0.213 / A→C 1.190
    #    其余非定义变量的效应量全部 |d|<0.3（danceability 仅 A→B 中等 0.514）。
    #
    # 【约束 2】阈值 0.5/0.5 是**约定值，不是自然断点**。
    #    阈值扰动实测（5 组）：
    #      ac≥0.40/en<0.60 → A=12874 B=4432 C=2243（最小 11.5%）
    #      ac≥0.45/en<0.55 → A=11839 B=4792 C=2918（最小 14.9%）
    #      ac≥0.50/en<0.50 → A=10694 B=5095 C=3760（最小 19.2%）← 基准
    #      ac≥0.55/en<0.45 → A=9485  B=5323 C=4741（最小 24.3%）
    #      ac≥0.60/en<0.40 → A=8243  B=5454 C=5852（最小 27.9%）
    #    **n 漂移最大 26.09%（4/18 项超 10%），但 mean_loudness 漂移 ≤3.99%、
    #    mean_tempo 漂移 ≤0.76%** → 准确表述是「质心稳定、边界敏感」：
    #    三分结构稳固（边界挪动不改变质心），但边界线两侧样本画像高度相似，
    #    说明**数据中不存在天然的三簇断层**。
    #    这与 era_quadrant 已锁定的「1960s 负峰度 −0.718 扁平平台」结论**互证** ——
    #    若存在天然三簇，峰度应为正；既然峰度为负且边界敏感，说明是连续谱上的约定切分。
    #    → 叙事须写「按约定边界切分的三段」，**不可写「数据自然分成三簇」**。
    #
    # 【约束 3】valence 只区分 A 与 {B, C}，**不区分 B 与 C**。
    #    A→B d=0.919（大）、A→C d=1.190（大），但 **B→C d=0.213（小）**。
    #    任何「情绪随风格线性递进」的表述都必须限定为「从 A 到 B 的跳升」，
    #    不能写成三段的线性梯度。
    #    同理 tempo 虽方向单调，但 η² 仅 0.0308、组内 sd 高达 27–30 BPM
    #    （极差 12.5 BPM 但组内方差极大），**不可作为独立判别依据**。
    #
    # ─────────────────────────────────────────────────────────────────
    #
    # 命名依据（数据无 genre 列，用 top artists 反推）：
    #   A acoustic_traditional：Frank Sinatra / Dean Martin / Johnny Cash /
    #     Bob Dylan / Bill Evans Trio / Nina Simone / John Coltrane /
    #     Ella Fitzgerald / Wes Montgomery / Nat King Cole
    #     → 传统流行 + 爵士 + 民谣 + 乡村。⚠️ **不可用 "Folk-Jazz Traditionalists"** ——
    #       Sinatra / Martin / Cole 是「传统流行」，既非 folk 也非严格 jazz；
    #       唯一能涵盖全部的上位词是「原声编制」。
    #   B transitional_pop：The Beach Boys / Elvis / The Beatles / Rolling Stones /
    #     Otis Redding / Sam Cooke / The Ventures / The Monkees
    #   C electric_rock：The Rolling Stones / The Kinks / The Who / The Animals /
    #     Led Zeppelin / Jimi Hendrix / Jefferson Airplane / CCR
    #
    # 三个子群的特征画像（实查）：
    #   A n=10694 (54.70%)  响度 −14.98  tempo 110.6  valence 0.444  sd_loudness 4.79
    #   B n=5095  (26.06%)  响度 −10.63  tempo 118.9  valence 0.662  sd_loudness 3.51
    #   C n=3760  (19.23%)  响度 −8.89   tempo 123.1  valence 0.709  sd_loudness 2.57
    #   → loudness 构成**完整的单调梯度**（唯一三对全部 ≥ 中等效应量的特征）；
    #     sd_loudness 递减（4.79 → 3.51 → 2.57）说明「老派」内部响度差异比「摇滚」大得多。
    #
    # 与其他视图的咬合（实查，仅比对确定性列 —— 遵守「禁止跨视图浮点等值断言」）：
    #   n 之和 = 10694 + 5095 + 3760 = 19549 == era_quadrant 的 1960s n
    #   acoustic_traditional 占比 54.70% == era_quadrant 1960s pct_hiac_loen
    #   electric_rock 占比 19.23%        == era_quadrant 1960s pct_loac_hien
    #   （象限占比同为整数计数派生，非浮点聚合，可直接互证）
    #
    # ⚠️ subgenre_label_zh 是**用户 2026-09-28 明确决定保留**的中文列：
    #    终端消费者是中文报告，中文标签进数据层可减少下游硬编码映射的维护成本；
    #    与 subgenre_label 构成函数依赖（一对一），不增加信息熵。
    #    若未来需国际化，只需新增 _en / _ja 列，不影响现有结构。
    #    故 GROUP BY 需同时含 1, 2（两个 CASE 列，互为函数依赖）。
    #
    # ⚠️ is_partial_decade 是常量 false（1960s 为完整十年）。
    #    它**没有信息量**，价值在**列契约的一致性** ——
    #    让下游可用统一方式过滤所有视图，无需为每个视图写特例。
    #    ⚠️ BOOLEAN 列**不能**放进 value_bounds（数值区间校验），只能用 null_check_columns 守。
    #    「必须为 false」用一次性验证确认（实测 3/3 全 false）。
    #
    # ⚠️ ORDER BY mean_acousticness DESC 是**语义序**（从最原声到最电声），
    #    无需额外 group_order 常量列。**排序不在校验范围内** ——
    #    断言查的是行数/集合/值域而非顺序，故未来调排序不会引发校验失败（有意留的松耦合）。
    (
        "sixties_subgenres",
        """CREATE OR REPLACE VIEW sixties_subgenres AS
SELECT CASE
         WHEN acousticness >= 0.5 AND energy <  0.5 THEN 'acoustic_traditional'
         WHEN acousticness <  0.5 AND energy >= 0.5 THEN 'electric_rock'
         ELSE 'transitional_pop'
       END  AS subgenre_label,
       CASE
         WHEN acousticness >= 0.5 AND energy <  0.5 THEN '原声传统（流行/爵士/民谣）'
         WHEN acousticness <  0.5 AND energy >= 0.5 THEN '电声摇滚'
         ELSE '过渡期流行'
       END  AS subgenre_label_zh,
       false AS is_partial_decade,
       count(*) AS n,
       round(count(*) * 100.0
             / (SELECT count(*) FROM raw_tracks WHERE year BETWEEN 1960 AND 1969), 2)
             AS pct_of_decade,
       avg(acousticness)      AS mean_acousticness,
       stddev(acousticness)   AS sd_acousticness,
       avg(energy)            AS mean_energy,
       stddev(energy)         AS sd_energy,
       avg(loudness)          AS mean_loudness,
       stddev(loudness)       AS sd_loudness,
       avg(tempo)             AS mean_tempo,
       avg(danceability)      AS mean_danceability,
       avg(valence)           AS mean_valence,
       avg(instrumentalness)  AS mean_instrumentalness,
       avg(duration_ms)       AS mean_duration_ms
FROM raw_tracks
WHERE year BETWEEN 1960 AND 1969
GROUP BY 1, 2
ORDER BY mean_acousticness DESC""",
        {
            "min_rows": 3,
            "max_rows": 3,
            "required_columns": [
                "subgenre_label",
                "subgenre_label_zh",
                "is_partial_decade",
                "n",
                "pct_of_decade",
                "mean_acousticness",
                "sd_acousticness",
                "mean_energy",
                "sd_energy",
                "mean_loudness",
                "sd_loudness",
                "mean_tempo",
                "mean_danceability",
                "mean_valence",
                "mean_instrumentalness",
                "mean_duration_ms",
            ],
            "column_types": {
                "subgenre_label": "VARCHAR",
                "subgenre_label_zh": "VARCHAR",
                "is_partial_decade": "BOOLEAN",
                "n": "BIGINT",
                "pct_of_decade": "DOUBLE",
                "mean_acousticness": "DOUBLE",
                "sd_acousticness": "DOUBLE",
                "mean_energy": "DOUBLE",
                "sd_energy": "DOUBLE",
                "mean_loudness": "DOUBLE",
                "sd_loudness": "DOUBLE",
                "mean_tempo": "DOUBLE",
                "mean_danceability": "DOUBLE",
                "mean_valence": "DOUBLE",
                "mean_instrumentalness": "DOUBLE",
                # avg(duration_ms) 输入是 BIGINT，但 avg 输出恒为 DOUBLE（DESCRIBE 实查）
                "mean_duration_ms": "DOUBLE",
            },
            "unique_columns": ["subgenre_label"],
            "null_check_columns": [
                "subgenre_label",
                "subgenre_label_zh",
                "is_partial_decade",
                "n",
                "pct_of_decade",
                "mean_acousticness",
                "sd_acousticness",
                "mean_energy",
                "sd_energy",
                "mean_loudness",
                "sd_loudness",
                "mean_tempo",
                "mean_danceability",
                "mean_valence",
                "mean_instrumentalness",
                "mean_duration_ms",
            ],
            "value_bounds": {
                # 下界 1000 = 子群样本量健康度红线；实测 3760–10694
                # （5 组阈值扰动下最小子群恒在 2243–5852，全部 ≥1000）
                "n": {"min": 1000, "max": 20000},
                "pct_of_decade": {"min": 0, "max": 100},
                "mean_acousticness": {"min": 0, "max": 1},
                "sd_acousticness": {"min": 0, "max": 1},
                "mean_energy": {"min": 0, "max": 1},
                "sd_energy": {"min": 0, "max": 1},
                "mean_loudness": {"min": -40, "max": 0},
                "sd_loudness": {"min": 0, "max": 10},
                "mean_tempo": {"min": 60, "max": 200},
                "mean_danceability": {"min": 0, "max": 1},
                "mean_valence": {"min": 0, "max": 1},
                "mean_instrumentalness": {"min": 0, "max": 1},
                "mean_duration_ms": {"min": 60000, "max": 600000},
            },
        },
    ),

    # ── 9. track_type_dispersion：器乐/人声两轨的分布形状，22 行 ──────
    #
    # 粒度 = (decade, track_type)，11 个十年 × 2 种类型 = 22 行。
    # 定位：instrumental_vs_vocal 的**统计精度升级版** —— 后者只给 mean_*，
    #       无法表达「分布形状」。本视图补 sd / 四分位 / 三段占比，
    #       支撑 D3 看板 Phase 2 的「双线 + IQR 带 + 三段占比堆叠」复合图。
    #
    # 核心叙事（2026-09-29 探查结论）：
    #   宏观均值显示「器乐 1970s 后进入平台期」，但这是**统计假象**。
    #   真相是器乐在 1970s 之后**裂变为两极**：低尾（ac<0.15，电声摇滚/金属，
    #   energy≈0.75 / loudness≈−9.2dB）与高尾（ac>0.85，古典/影视配乐，
    #   energy≈0.13 / loudness≈−22.4dB）各占约 1/3，中段只剩 23–30%。
    #   两尾响度差 13.2 dB —— 是两个制作世界，不是程度差异。
    #   人声曲则相反：始终单峰（中段占 42–46%），整条分布平滑左移。
    #
    # ⚠️ 【约束 1】禁止用 mean_acousticness 单独描述器乐曲的「趋势」。
    #    1970s 之后器乐均值冻结在 0.47，但该值**落在双峰之间的空谷**，
    #    既不代表低尾（0.01 的电子乐）也不代表高尾（0.93 的古典）。
    #    参照 ratio = (低尾+高尾)/中段，实测 1980s 3.33 / 1990s 3.01 /
    #    2000s 2.29 / 2010s 2.74 —— 器乐恒高于人声（1.14–1.41）。
    #    下游若只画均值线，会得出「器乐进入稳定平台期」的错误结论。
    #
    # ⚠️ 【约束 2】1960s 器的双峰比 1.54 是**全表最低**（不是最高）。
    #    1920s 的 55.49 也不代表「强双峰」，而是「97.2% 挤在高尾」的极端单峰。
    #    双峰比这一指标**不能独立区分**「单峰极端集中」与「真双峰」，
    #    必须配合三段占比同看。故本视图同时给出三个 pct_* 列。
    #
    # ⚠️ 【约束 3】2020s 器乐 n = 28，**不可用于任何趋势解读**。
    #    95% CI = [0.316, 0.653]，**完全覆盖 2010s 点值 0.4582**，
    #    无法证明统计上任何「回升」。其 28 首内容物为 Chopin 钢琴 +
    #    雨声环境音 + Ólafur Arnalds 等杂样，两尾占 21/28 = 75%。
    #    下游必须用虚线 + 空心点 + 半径编码 n 做三层视觉降级。
    #
    # 分段占比阈值 0.15 / 0.85 经门槛稳健性检验：
    #   换 instrumentalness 门槛 0.3 / 0.5 / 0.7，三段占比形状几乎不变
    #   （1990s 双峰比 2.96 / 3.01 / 2.98；2010s 2.56 / 2.74 / 2.90）
    #   → 双峰结构对分类门槛不敏感，是真结构，不是切分伪影。
    #
    # ⚠️ DDL 陷阱（2026-09-29 实测踩中并修复）：
    #    初版 pct_of_decade 用**关联标量子查询**取该十年总数，形如
    #      round(count(*) * 100.0 / (SELECT count(*) FROM raw_tracks r2
    #            WHERE r2.year // 10 * 10 = year // 10 * 10), 2)
    #    → 子查询里的 `year` 被解析成**内层 r2.year**（内层作用域优先），
    #      条件退化为恒真，分母变成全表 170,653 行。
    #      症状：1920s 器乐输出 1.22%（应为 40.77%），**不报错、静默错误**。
    #    → 修复：改用窗口函数 `round(n * 100.0 / sum(n) OVER
    #      (PARTITION BY decade), 2)`，用 CTE 把 decade 先物化，彻底避开关联。
    #      实测修复后 1920s 器乐 40.77% + 人声 59.23% = 100.00%。
    #    **教训：跨行总量一律用窗口函数，不用关联子查询 —— 后者在内外同名列
    #      存在时会静默把作用域解析到内层。**
    #
    # 类型实查（DESCRIBE，2026-09-29）：
    #    raw sum(CASE...) → HUGEINT（BIGINT 溢出提升，与 era_quadrant 同源），
    #    但所有派生列均经 round(x * 100.0 / count(*), n) 包成 DOUBLE。
    #    本视图**不暴露裸 sum 列**，无 HUGEINT 断言风险。
    #
    # 四个「一次性验证」（不写进 validate_rules —— 七键无法表达列间约束）：
    #   1. 三段占比之和 ∈ [99.9, 100.1]：**22/22 通过**（实测 99.99–100.01，
    #      偏差全部来自 round(...,2) 的舍入，非数据错误）
    #   2. 每年代 sum(n) == acoustic_trajectory.n：**11/11 精确相等**
    #      （证明本视图是整体的完整分解，无样本遗漏/重复）
    #   3. is_partial_decade 仅 2020s 两行为 true：**通过**
    #   4. mean_acousticness 与 instrumental_vs_vocal 4 位小数一致：
    #      **22/22 通过**；原始最大绝对差 **2.22e-16（1 ULP）** ——
    #      正是 DuckDB 并行归约的浮点非结合性。故此处**用 4 位小数容差
    #      比对，而非逐行等值断言**（遵守本技能「禁止跨视图浮点等值断言」）。
    (
        "track_type_dispersion",
        """CREATE OR REPLACE VIEW track_type_dispersion AS
WITH base AS (
    SELECT year // 10 * 10                           AS decade,
           CASE WHEN instrumentalness >= 0.5
                THEN 'instrumental' ELSE 'vocal' END AS track_type,
           acousticness
    FROM raw_tracks
    WHERE year IS NOT NULL
),
agg AS (
    SELECT decade,
           track_type,
           count(*)                                  AS n,
           avg(acousticness)                         AS mean_acousticness,
           stddev(acousticness)                      AS sd_acousticness,
           quantile_cont(acousticness, 0.25)         AS p25_acousticness,
           quantile_cont(acousticness, 0.50)         AS median_acousticness,
           quantile_cont(acousticness, 0.75)         AS p75_acousticness,
           round(sum(CASE WHEN acousticness <  0.15 THEN 1 ELSE 0 END)
                 * 100.0 / count(*), 2)              AS pct_low_tail,
           round(sum(CASE WHEN acousticness BETWEEN 0.15 AND 0.85 THEN 1 ELSE 0 END)
                 * 100.0 / count(*), 2)              AS pct_mid,
           round(sum(CASE WHEN acousticness >  0.85 THEN 1 ELSE 0 END)
                 * 100.0 / count(*), 2)              AS pct_high_tail
    FROM base
    GROUP BY 1, 2
)
SELECT decade,
       track_type,
       (decade = 2020)                               AS is_partial_decade,
       n,
       mean_acousticness,
       sd_acousticness,
       p25_acousticness,
       median_acousticness,
       p75_acousticness,
       pct_low_tail,
       pct_mid,
       pct_high_tail,
       round(n * 100.0 / sum(n) OVER (PARTITION BY decade), 2) AS pct_of_decade
FROM agg
ORDER BY 1, 2""",
        {
            "min_rows": 22,
            "max_rows": 22,
            "required_columns": [
                "decade",
                "track_type",
                "is_partial_decade",
                "n",
                "mean_acousticness",
                "sd_acousticness",
                "p25_acousticness",
                "median_acousticness",
                "p75_acousticness",
                "pct_low_tail",
                "pct_mid",
                "pct_high_tail",
                "pct_of_decade",
            ],
            "column_types": {
                "decade": "BIGINT",
                "track_type": "VARCHAR",
                "is_partial_decade": "BOOLEAN",
                "n": "BIGINT",
                "mean_acousticness": "DOUBLE",
                "sd_acousticness": "DOUBLE",
                "p25_acousticness": "DOUBLE",
                "median_acousticness": "DOUBLE",
                "p75_acousticness": "DOUBLE",
                # 三段占比均经 round(sum(CASE...) * 100.0 / count(*), 2) 包成 DOUBLE，
                # 规避 sum(BIGINT) → HUGEINT 的溢出提升（DESCRIBE 实查确认）
                "pct_low_tail": "DOUBLE",
                "pct_mid": "DOUBLE",
                "pct_high_tail": "DOUBLE",
                "pct_of_decade": "DOUBLE",
            },
            "unique_columns": ["decade", "track_type"],
            "null_check_columns": [
                "decade",
                "track_type",
                "is_partial_decade",
                "n",
                "mean_acousticness",
                "sd_acousticness",
                "p25_acousticness",
                "median_acousticness",
                "p75_acousticness",
                "pct_low_tail",
                "pct_mid",
                "pct_high_tail",
                "pct_of_decade",
            ],
            "value_bounds": {
                "mean_acousticness":   {"min": 0, "max": 1},
                "sd_acousticness":     {"min": 0, "max": 1},
                "p25_acousticness":    {"min": 0, "max": 1},
                "median_acousticness": {"min": 0, "max": 1},
                "p75_acousticness":    {"min": 0, "max": 1},
                "pct_low_tail":        {"min": 0, "max": 100},
                "pct_mid":             {"min": 0, "max": 100},
                "pct_high_tail":       {"min": 0, "max": 100},
                "pct_of_decade":       {"min": 0, "max": 100},
                # 下界 1：2020s 器乐实测仅 28 行（残缺十年 + 器乐稀有），
                # 不可设 1000 —— 那会让闸门在真实数据上误报。
                # 低样本的可信度问题由前端视觉降级 + 一次性验证承载，不在此处拦。
                "n": {"min": 1, "max": 25000},
            },
        },
    ),
    # ── 10. song_version_study_clean：清洗后的天然实验，81 行 ─────────
    # 2026-09-29 新增（D3 看板 Phase 3 的数据底座）。支撑报告 §3.4
    # 「控制词曲变量、只观察制作风格时间效应」的**净效应**版本。
    #
    # 【为什么必须清洗】Phase 3 探查把 song_version_study 的「对象固定」前提
    # 判为**部分不成立**，实锤三类污染：
    #   ① 泛用名 / 同题异曲（5 首）：overture 46 轨 33 艺人（罗西尼/威尔第/
    #      莫扎特 + 百老汇 + The Who + Daft Punk，无共同作品）；summertime 混入
    #      DJ Jazzy Jeff 说唱与 Kenny Chesney 乡村；i love you 混入 Black Flag
    #      与 Barney(52 秒)；joy to the world 混入 Three Dog Night 的
    #      「Jeremiah was a bullfrog」；ave maria 是舒伯特 / 巴赫-古诺 / 卡契尼
    #      三首同题异曲。**这 5 首直接击穿「同一首作品」的前提。**
    #      ⚠️ 原台账注释声称 n_decades_multi >= 7 能过滤泛用名 —— 实测把
    #      overture(7) 与 i love you(8) 放了进来，该判据对这两首无效。
    #   ② 年份字段不等于录音年：year == left(release_date,4) 647/647 命中，
    #      但 release_date 是**专辑发行日**。用「作品创作年」做硬约束检出
    #      16 行物理不可能（Doris Day 的 The Christmas Song 标为 1932，该曲
    #      1944 才写成；Bing Crosby 的 Silver Bells 标为 1945，该曲 1950 才写成）。
    #      **全部落在 1932–1949，1950 年后零违例。**
    #   ③ 同一录音换专辑重发会拿到**新的 track id** 并跨十年复现
    #      （Frank Sinatra 的 Have Yourself 同时出现在 1945 与 1994）。
    #
    # 【清洗三层，实测级联】行级池 647 行 / 15 首
    #      → 剔 5 首污染曲目：457 行 / 10 首
    #      → 创作年硬约束：445 行（剔 12 行）
    #      → 同录音去重：436 行（9 组重复、剔 9 行）
    #      → 重新聚合到 (song_key, decade)：**81 行 / 10 首 / 9 个十年**
    #
    # 【曲目池设计：继承而不二次筛选】曲目池 = `song_version_study` 的 15 首
    #   ∪ 减去 5 首污染曲目，**不在清洗层重设任何阈值**。这样两视图的曲目口径
    #   严格可比，避免「清洗 + 调阈值」双重变更导致无法归因。
    #   ⚠️ 若沿用原阈值（n_decades>=8 AND fy<=1949）会对清洗后的池误伤：
    #      silver bells 创作年 1950，其 1940s 记录全是物理错误，清洗后
    #      n_decades 由 8 降为 7、first_year 由 1945 升为 1953，被旧阈值剔掉
    #      → 结果是 74 行 / 9 首。本视图刻意不采用该口径，以保住 10 首的
    #      小多图网格。**两种口径的行数差异已记录，供复核时对照。**
    #
    # 【去重键：不是 id，是 (song_key, artists, duration_ms)】
    #   ⚠️ `id` 在本池内 647/647 全唯一（重发拿到新 id），用它去重**等于没做**。
    #   (song_key, artists, duration_ms) 实测 15 组重复、15 行超额，
    #   其中 1 组跨十年（Kidsongs 的 jingle bells 1993 与 2011，同时长同原声度）。
    #   保留最早的一年（ORDER BY year, id）作为该录音的代表年。
    #   ⚠️ 分区键必须用**原始 artists 串**，不能用下面清洗后的 artist_name ——
    #      后者取首个艺人，会把 ['Bing Crosby'] 与 ['Bing Crosby','Ken Darby Singers']
    #      误判为同一录音（同曲同时长时）。
    #
    # 【创作年表】只收录本池 10 首（污染 5 首不需要）。口径 = 可考最早公开年份，
    #   宁松勿紧：过松只漏个别脏行，过紧会误杀合法早期录音。
    #     silent night 1818 / white christmas 1942 / winter wonderland 1934 /
    #     jingle bells 1857 / have yourself… 1943 / the christmas song 1944 /
    #     silver bells 1950 / santa claus is coming to town 1934 /
    #     sleigh ride 1948 / i'll be home for christmas 1943
    #
    # ⚠️【DDL 转义坑】曲名 `i'll be home for christmas` 含撇号，在单引号 SQL
    #    字面量里必须写成 'i''ll be home for christmas'。直接写 'i'll…' 会让
    #    DuckDB 抛 `Parser Error: syntax error at or near "ll"`。
    #    （此前试过 $$…$$ 美元引用，可用；但 '' 转义更通用，本 DDL 采用后者。）
    #
    # ⚠️【艺人串清洗坑】raw_tracks.artists 是 Python 风格列表串，且**两种引号风格
    #    并存**：['Bing Crosby'] 与 ["Alexander O'Neal"]。必须同时去单双引号。
    #    正确写法是**只 trim 首尾**：
    #      trim(replace(split_part(artists, ',', 1), '[', ''), ' ''"[]')
    #    ❌ 用 replace(..., '''','') 全局删撇号会把 Booker T. & the M.G.'s 弄成
    #       M.G.s（丢失撇号）。trim 只削首尾，艺名内部撇号得以保留。
    #    逗号安全性已实测：647 条中含逗号 93 条，**逗号后不接引号的 0 条**
    #    → 逗号恒为艺人分隔符，split_part(...,',',1) 取首个艺人安全。
    #
    # ⚠️【取极值艺人】用有序集聚合 first/last(x ORDER BY 值, id)：
    #      first(artist_name ORDER BY acousticness, id) AS artist_low
    #    第二排序键 id 是**必需的**——原声度浮点相等时（实测有多组）若不指定
    #    第二键，同一份数据可能给出不同艺人，断言无法复现。
    #
    # ⚠️ n_versions_total 类型是 HUGEINT（sum(BIGINT) 的溢出提升），
    #    与 song_version_study 同源同型；n_decades / n_decades_multi 是 BIGINT。
    #
    # 【value_bounds 口径】比例类固定 0–1；n_decades / n_decades_multi 锁 7–10
    #   （下界 7 = silver bells 实测值，是清洗后可达的最小覆盖）；
    #   n_versions_total 下界 25 = 继承自源视图的 vtot>=25 门槛，上界 200 留裕量；
    #   year 下界 1800（早于本池最早的创作年 1818）；n_versions 上界 60（实测最大 21）。
    #
    # 【八项一次性验证（2026-09-29 实跑，ALL PASS）】
    #   1) 创作年硬约束生效：视图内 year_min < composed_year 的行 = 0
    #   2) 5 首污染曲目残留 = 0 行 / 0 曲目
    #   3) 同录音去重：445 → 436（9 组、9 行）
    #   4) 曲目池 = 15 首 − 5 首，差集为空（10/10）
    #   5) 行数 81 = 唯一 (song_key, decade) 组合数 81（无意外丢格）
    #   6) **池化谷底仍为 1980s**：等权 0.6136 / 版本量加权 0.5823，两口径一致
    #      → 这是 Phase 3 小多图的 1980s 参考线的成立依据
    #   7) 格数合计 = 81；thin_cell ≡ (n_versions <= 2) 口径不一致行 = 0
    #   8) Silent Night 深潜锚点：1980s 最低 = Bon Jovi 0.0914（全曲最低）；
    #      2010s 最高 = Michael Bublé 0.959；Δ = 0.8676
    #      ⚠️ **年份修正**：Bublé 那条是 **2011 年**，不是 Phase 3 探查稿里的
    #      2012 —— 2012 是同一录音（227520ms）的重复条目，已被去重规则剔除。
    #
    # 【叙事依赖（前端若改动必须同步改这里）】
    #   - 谷底 = 1980s（1970s–1990s 是宽谷：0.6721 / 0.6136 / 0.6225）
    #   - 10 首曲目池名单固定；thin_cell 共 15 个，分布在 9 首歌
    #   - 缺失格子 19 个（1930s 多数曲目尚未写成；2020s 全空）
    (
        "song_version_study_clean",
        """CREATE OR REPLACE VIEW song_version_study_clean AS
WITH song_meta(song_key, composed_year) AS (
    VALUES
        ('silent night', CAST(1818 AS BIGINT)),
        ('white christmas', CAST(1942 AS BIGINT)),
        ('winter wonderland', CAST(1934 AS BIGINT)),
        ('jingle bells', CAST(1857 AS BIGINT)),
        ('have yourself a merry little christmas', CAST(1943 AS BIGINT)),
        ('the christmas song', CAST(1944 AS BIGINT)),
        ('silver bells', CAST(1950 AS BIGINT)),
        ('santa claus is coming to town', CAST(1934 AS BIGINT)),
        ('sleigh ride', CAST(1948 AS BIGINT)),
        ('i''ll be home for christmas', CAST(1943 AS BIGINT))
),
song_pool AS (
    SELECT DISTINCT song_key
    FROM song_version_study
    WHERE song_key NOT IN ('overture', 'summertime', 'i love you', 'joy to the world', 'ave maria')
),
raw_pool AS (
    SELECT lower(trim(name)) AS song_key,
           artists,
           trim(replace(split_part(artists, ',', 1), '[', ''), ' ''"[]') AS artist_name,
           year,
           id,
           duration_ms,
           acousticness,
           year // 10 * 10 AS decade
    FROM raw_tracks
    WHERE year IS NOT NULL AND name IS NOT NULL
      AND lower(trim(name)) IN (SELECT song_key FROM song_pool)
),
stage1 AS (
    SELECT r.*
    FROM raw_pool r
    JOIN song_meta m ON r.song_key = m.song_key
    WHERE r.year >= m.composed_year
),
stage2 AS (
    SELECT *,
           row_number() OVER (
               PARTITION BY song_key, artists, duration_ms
               ORDER BY year, id
           ) AS rn
    FROM stage1
),
clean_pool AS (
    SELECT * FROM stage2 WHERE rn = 1
),
per_decade AS (
    SELECT song_key,
           decade,
           count(*)          AS n_versions,
           avg(acousticness) AS mean_acousticness,
           min(acousticness) AS min_acousticness,
           max(acousticness) AS max_acousticness,
           first(artist_name ORDER BY acousticness, id) AS artist_low,
           last (artist_name ORDER BY acousticness, id) AS artist_high,
           min(year) AS year_min,
           max(year) AS year_max
    FROM clean_pool
    GROUP BY 1, 2
),
stats AS (
    SELECT song_key,
           count(*)                                AS n_decades,
           count(*) FILTER (WHERE n_versions >= 2) AS n_decades_multi,
           sum(n_versions)                         AS n_versions_total
    FROM per_decade
    GROUP BY 1
)
SELECT p.song_key,
       p.decade,
       (p.decade = 2020) AS is_partial_decade,
       p.n_versions,
       p.mean_acousticness,
       p.min_acousticness,
       p.max_acousticness,
       p.max_acousticness - p.min_acousticness AS ac_range,
       p.artist_low,
       p.artist_high,
       p.year_min,
       p.year_max,
       (p.n_versions <= 2) AS thin_cell,
       s.n_decades,
       s.n_decades_multi,
       s.n_versions_total
FROM per_decade p
JOIN stats s ON p.song_key = s.song_key
ORDER BY p.song_key, p.decade""",
        {
            # 精确值：81 = 10 首 × 各自 7–9 个十年，实测无重复年份组合
            "min_rows": 81,
            "max_rows": 81,
            "required_columns": [
                "song_key",
                "decade",
                "is_partial_decade",
                "n_versions",
                "mean_acousticness",
                "min_acousticness",
                "max_acousticness",
                "ac_range",
                "artist_low",
                "artist_high",
                "year_min",
                "year_max",
                "thin_cell",
                "n_decades",
                "n_decades_multi",
                "n_versions_total",
            ],
            "column_types": {
                "song_key": "VARCHAR",
                "decade": "BIGINT",
                "is_partial_decade": "BOOLEAN",
                "n_versions": "BIGINT",
                "mean_acousticness": "DOUBLE",
                "min_acousticness": "DOUBLE",
                "max_acousticness": "DOUBLE",
                "ac_range": "DOUBLE",
                "artist_low": "VARCHAR",
                "artist_high": "VARCHAR",
                "year_min": "BIGINT",
                "year_max": "BIGINT",
                "thin_cell": "BOOLEAN",
                "n_decades": "BIGINT",
                "n_decades_multi": "BIGINT",
                # ⚠️ HUGEINT（sum(BIGINT) 的溢出提升），与源视图同源同型
                "n_versions_total": "HUGEINT",
            },
            # (song_key, decade) 二维键唯一 —— 均为确定性列
            "unique_columns": ["song_key", "decade"],
            "null_check_columns": [
                "song_key",
                "decade",
                "is_partial_decade",
                "n_versions",
                "mean_acousticness",
                "min_acousticness",
                "max_acousticness",
                "ac_range",
                "artist_low",
                "artist_high",
                "year_min",
                "year_max",
                "thin_cell",
                "n_decades",
                "n_decades_multi",
                "n_versions_total",
            ],
            "value_bounds": {
                "decade": {"min": 1800, "max": 2020},
                # 上界 60 留裕量（实测最大 21）；下界 1 因为薄格子可为单版本
                "n_versions": {"min": 1, "max": 60},
                "mean_acousticness": {"min": 0, "max": 1},
                "min_acousticness": {"min": 0, "max": 1},
                "max_acousticness": {"min": 0, "max": 1},
                "ac_range": {"min": 0, "max": 1},
                "year_min": {"min": 1800, "max": 2020},
                "year_max": {"min": 1800, "max": 2020},
                # 下界 7 = silver bells（创作年 1950，1940s 记录全属物理错误）
                # 清洗后的实际覆盖，是清洗后池可达的最小值
                "n_decades": {"min": 7, "max": 10},
                "n_decades_multi": {"min": 7, "max": 10},
                # 下界 25 = 继承自 song_version_study 的 vtot>=25 门槛
                "n_versions_total": {"min": 25, "max": 200},
            },
        },
    ),
]


def run_all(db_path: str | None = None, verbose: bool = True) -> list[dict]:
    """按锁定顺序逐个创建并校验。任一失败即断链，后续视图一律不建。"""
    results: list[dict] = []
    for name, sql, rules in VIEWS:
        r = create_and_validate_view(name, sql, rules, db_path=db_path or DB_PATH)
        results.append(r)
        if verbose:
            mark = "PASS" if r["status"] == "VALID" else "FAIL"
            print(f"[{mark}] {name}  rows={r.get('rows')}  code={r.get('code')}")
            if r["status"] != "VALID":
                print(f"        reason: {r.get('reason')}")
                print("        → 断链：后续视图不再创建")
                break
            print("        断言: " + " ".join(f"{k}={v}" for k, v in r["assertions"].items()))
            print()
    return results

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    res = run_all()
    ok = sum(1 for r in res if r["status"] == "VALID")
    print("=" * 74)
    print(f"汇总：{ok}/{len(VIEWS)} 视图通过校验（status=VALID）")
    print("=" * 74)
    print()
    print("完整 JSON 凭证：")
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    sys.exit(0 if ok == len(VIEWS) else 1)
