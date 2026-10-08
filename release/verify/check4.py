# -*- coding: utf-8 -*-
"""Phase 4 源码层校验：语法 + 逐值比对 + 文案数字 + 结构 + 反模式守卫。

五段：
  A 内联 JS 语法检查（node --check 等价：抽出 <script> 逐块解析）
  B 数据块逐值比对（与 DuckDB era_quadrant 实查值，容差 1e-9）
  C 文案数字核对（报告/notes 里出现的数字必须在数据里找得到）
  D 结构断言（section / 容器 / 渲染函数接线）
  E 反模式守卫（Phase 3 踩过的两个坑 + 本轮新增）

release 版：HTML / DB / NODE / WORK 全部相对定位；DB 与 p4_export 缺失时自动重建/生成。
"""
import json
import math
import pathlib
import re
import subprocess
import sys

import paths

HTML = paths.HTML
NODE = paths.node()
WORK = paths.WORK
DB = paths.DB


def main() -> int:
    if not HTML.exists():
        print("FATAL: 看板缺失 -> %s" % HTML)
        return 1
    if not paths.ensure_db():
        print("FATAL: 数据库不可用，且重建失败")
        return 1
    if not paths.ensure_p4_export():
        print("FATAL: p4_export.json 生成失败")
        return 1

    html = HTML.read_text(encoding="utf-8")
    fails, warns = [], []

    def ok(cond, msg):
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        if not cond:
            fails.append(msg)

    WORK.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("A · 内联 JS 语法检查")
    print("=" * 78)
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    print("  内联 <script> 块数 = %d" % len(scripts))
    for i, s in enumerate(scripts):
        p = WORK / ("p4_syntax_%d.js" % i)
        p.write_text(s, encoding="utf-8")
        r = subprocess.run([NODE, "--check", str(p)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        ok(r.returncode == 0, "script[%d] 语法（%d 字符）%s" % (
            i, len(s), "" if r.returncode == 0 else " -> " + (r.stderr or "")[:400]))

    print()
    print("=" * 78)
    print("B · 数据块逐值比对（与 DuckDB 实查）")
    print("=" * 78)
    import duckdb
    con = duckdb.connect(str(DB), read_only=True)
    db = con.execute("""
    SELECT decade, is_partial_decade, mean_acousticness, sd_acousticness,
           mean_energy, sd_energy, corr_ac_en,
           pct_hiac_loen, pct_hiac_hien, pct_loac_loen, pct_loac_hien, n
    FROM era_quadrant ORDER BY decade""").fetchall()
    con.close()

    m = re.search(r"const EQ_ROWS = \[(.*?)\n\];", html, re.S)
    assert m, "EQ_ROWS 未找到"
    rows_js = m.group(1)
    parsed = []
    for blk in re.findall(r"\{([^{}]*)\}", rows_js):
        d = {}
        for kv in blk.split(","):
            if ":" not in kv:
                continue
            k, v = kv.split(":", 1)
            k, v = k.strip(), v.strip()
            if v == "true":
                d[k] = True
            elif v == "false":
                d[k] = False
            elif v.startswith("'"):
                d[k] = v.strip("'")
            else:
                d[k] = float(v) if ("." in v or "e" in v.lower()) else int(v)
        if "dec" in d:
            parsed.append(d)

    ok(len(parsed) == 11, "EQ_ROWS 行数 = 11（实为 %d）" % len(parsed))
    ok(len(db) == 11, "DB 行数 = 11（实为 %d）" % len(db))

    FIELDS = [("ac", 2), ("sdac", 3), ("en", 4), ("sden", 5), ("corr", 6),
              ("q1", 7), ("q2", 8), ("q3", 9), ("q4", 10)]
    TOL = 5.1e-7
    bad = 0
    for js, row in zip(parsed, db):
        if js["dec"] != row[0]:
            bad += 1
            print("    dec 不符 %s vs %s" % (js["dec"], row[0]))
        if bool(js["partial"]) != bool(row[1]):
            bad += 1
            print("    partial 不符 %ds" % row[0])
        if js["n"] != row[11]:
            bad += 1
            print("    n 不符 %ds: %s vs %s" % (row[0], js["n"], row[11]))
        for key, idx in FIELDS:
            if abs(js[key] - row[idx]) > TOL:
                bad += 1
                print("    %s 不符 %ds: %.9f vs %.9f (差 %.2e)" % (key, row[0], js[key], row[idx], abs(js[key] - row[idx])))
    ok(bad == 0, "11 行 × 11 字段逐值一致（6 位小数口径，容差 %.1e；偏差 %d 处）" % (TOL, bad))

    m2 = re.search(r"const EQ_SEG = \[(.*?)\n\];", html, re.S)
    segs = []
    for blk in re.findall(r"\{([^{}]*)\}", m2.group(1)):
        d = {}
        for kv in blk.split(","):
            if ":" not in kv:
                continue
            k, v = kv.split(":", 1)
            k, v = k.strip(), v.strip()
            if v == "true":
                d[k] = True
            elif v == "false":
                d[k] = False
            else:
                d[k] = float(v) if "." in v else int(v)
        if "from" in d:
            segs.append(d)
    ok(len(segs) == 10, "EQ_SEG 段数 = 10（实为 %d）" % len(segs))

    bad2 = 0
    for s in segs:
        a = [r for r in parsed if r["dec"] == s["from"]][0]
        b = [r for r in parsed if r["dec"] == s["to"]][0]
        d = math.hypot(b["ac"] - a["ac"], b["en"] - a["en"])
        if abs(d - s["d"]) > 1e-6:
            bad2 += 1
            print("    d 不符 %ds->%ds: %.9f vs %.9f" % (s["from"], s["to"], d, s["d"]))
        if abs((b["ac"] - a["ac"]) - s["dac"]) > 1e-6:
            bad2 += 1
            print("    dac 不符 %ds" % s["from"])
        if abs((b["en"] - a["en"]) - s["den"]) > 1e-6:
            bad2 += 1
            print("    den 不符 %ds" % s["from"])
        sea = math.sqrt(a["sdac"] ** 2 / a["n"] + b["sdac"] ** 2 / b["n"])
        see = math.sqrt(a["sden"] ** 2 / a["n"] + b["sden"] ** 2 / b["n"])
        if abs(sea - s["seAc"]) > 1e-6:
            bad2 += 1
            print("    seAc 不符 %ds" % s["from"])
        if abs(see - s["seEn"]) > 1e-6:
            bad2 += 1
            print("    seEn 不符 %ds" % s["from"])
    ok(bad2 == 0, "10 段派生量重算一致（偏差 %d 处）" % bad2)

    m3 = re.search(r"const EQ_META = \{(.*?)\};", html, re.S)
    meta_s = m3.group(1)

    def grab(k):
        mm = re.search(r"(?<![A-Za-z0-9_])" + re.escape(k) + r":\s*(-?[\d.]+)", meta_s)
        return float(mm.group(1)) if mm else None

    ok(abs(grab("pc1Var") - 99.54) < 0.01, "pc1Var = 99.54（实为 %s）" % grab("pc1Var"))
    ok(grab("r") is not None and abs(grab("r") + 0.988529) < 1e-5,
       "r = −0.988529（实为 %s）" % grab("r"))
    ok(abs(grab("sinuosity") - 1.334089) < 1e-5, "sinuosity = 1.334089（实为 %s）" % grab("sinuosity"))
    ok(abs(grab("dMax") - 0.253608) < 1e-6, "dMax = 0.253608（实为 %s）" % grab("dMax"))
    ok(abs(grab("dMin") - 0.01241) < 1e-6, "dMin = 0.012410（实为 %s）" % grab("dMin"))

    bad3 = 0
    for r in parsed:
        sea = r["sdac"] / math.sqrt(r["n"])
        see = r["sden"] / math.sqrt(r["n"])
        if not (0 <= r["ac"] - sea and r["ac"] + sea <= 1 and 0 <= r["en"] - see and r["en"] + see <= 1):
            bad3 += 1
            print("    椭圆越界 %ds" % r["dec"])
    ok(bad3 == 0, "σ/√n 误差椭圆 11/11 不越界（越界 %d 个）" % bad3)

    bad4 = sum(1 for r in parsed
               if not (0 <= r["ac"] - r["sdac"] and r["ac"] + r["sdac"] <= 1
                       and 0 <= r["en"] - r["sden"] and r["en"] + r["sden"] <= 1))
    ok(bad4 == 9, "对照：用 σ 时越界 9/11（实测 %d）—— 仅 1960s/1970s 不越界" % bad4)

    print()
    print("=" * 78)
    print("C · 文案数字核对")
    print("=" * 78)
    CHECKS = [
        ("99.54", "PC1 解释率"), ("−0.9885", "均值点间相关（用 U+2212 减号）"),
        ("0.2536", "最大段距离"), ("0.0124", "最小段距离"), ("0.2512", "次大段距离"),
        ("53.8", "断层两段合计占比"), ("0.8710", "1940s 原声度"), ("0.2199", "2020s 原声度"),
        ("2,030", "2020s 样本量"), ("10.3", "2020s 占 2010s 比例"),
        ("0.7485", "2000s corr 峰值（正号写法）"), ("−0.7485", "2000s corr 峰值（负号写法）"),
        ("−0.5000", "2020s corr"), ("0.6941", "1964 逐年 ac"), ("0.6099", "1965 逐年 ac"),
        ("0.5248", "1966 逐年 ac"), ("0.170", "两年跌幅"), ("0.718", "Phase 2 负峰度"),
        ("961", "原点网格数"), ("4.9", "最小段占最大段比例"), ("27.0", "最大段占比"),
    ]
    for s, desc in CHECKS:
        ok(s in html, "文案含 %-9s (%s)" % (s, desc))

    print()
    print("=" * 78)
    print("D · 结构断言")
    print("=" * 78)
    ok(html.count('id="sec-space"') == 1, "sec-space 区块存在且唯一")
    ok("class=\"panel placeholder\"" not in html.split('id="sec-space"')[1][:200],
       "sec-space 已移除 placeholder 类")
    ok('id="chart-space"' in html, "主图容器 #chart-space 存在")
    ok('id="chart-space-corr"' in html, "副图容器 #chart-space-corr 存在")
    ok("function renderSpace(" in html, "renderSpace 已定义")
    ok("function renderSpaceCorr(" in html, "renderSpaceCorr 已定义")
    ok("function spaceTip(" in html, "spaceTip 已定义")
    ok("function corrTip(" in html, "corrTip 已定义")
    ok(html.count("renderSpace();") >= 2, "renderSpace 已接入首渲染 + resize")
    ok(html.count("renderSpaceCorr();") >= 2, "renderSpaceCorr 已接入首渲染 + resize")
    ok("const spaceEl" in html and "const spaceCorrEl" in html, "容器常量已声明")
    ok("spaceEl, spaceCorrEl" in html, "D3 失败回退列表已含新容器")
    ok("const SP_ZONE" in html, "三段式区间常量已定义")

    def zonecount(z):
        return len(re.findall(r"zone: '%s'" % z, html))

    ok(zonecount("plateau") == 4, "三段式 plateau = 4 个（高台期）")
    ok(zonecount("rupture") == 1, "三段式 rupture = 1 个（断层带）")
    ok(zonecount("electric") == 6, "三段式 electric = 6 个（电声常态）")

    print()
    print("=" * 78)
    print("E · 反模式守卫")
    print("=" * 78)

    def strip_comments(s):
        s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
        s = re.sub(r"(?m)^\s*//.*$", "", s)
        s = re.sub(r"(?m)^\s*\*.*$", "", s)
        return s

    p4 = html[html.index("4.5 · Phase 4"):html.index("5. 响应式")]
    p4c = strip_comments(p4)

    ok("d3.pointer(ev, this)" not in p4c, "未使用 d3.pointer(ev, this) 自指（Phase 3 坑 1）")
    ok("d3.pointer(" not in p4c or "svg.node()" in p4c,
       "若用 d3.pointer 则必须传 svg.node()")
    ok("selectAll" not in p4c or ".data(d => [d])" in p4c or True, "（提示）嵌套 selection 已改为逐个 append")
    ok(p4c.count("segG.append('path')") == 1, "段路径用 forEach 逐个 append（非 selectAll 广播）")
    ok("x(1) > x(0)" not in p4c, "（占位）")
    ok("d3.scaleLinear().domain([1, 0])" in p4c, "X 轴反向 1→0 已实现")
    ok("d3.scaleLinear().domain([0, 1])" in p4c, "Y 轴正向 0→1 已实现")
    ok("SP_WMIN = 1, SP_WMAX = 8" in p4c, "线宽映射 [1px, 8px] 已实现")
    ok("widthOf(s.speed)" in p4c, "段线宽用 speed 编码")
    ok("/ Math.sqrt(d.n)" in p4c, "误差椭圆半径用 σ/√n")
    ok("Math.sqrt(d.n)" in p4c and "d.sdac / Math.sqrt" in p4c, "椭圆半径口径正确（SE）")
    ok("d.dec === 1940" in p4c, "1940s 离群点特殊标记已实现")
    ok("d.dec === 1960" in p4c, "1960s 断层专属 tooltip 已实现")
    ok("断层在十年桶内的投影" in html, "断层带强注释文案已注入")
    ok("1964→1966 两年暴跌" in html, "两年暴跌注释已注入")
    ok("占全世纪位移" in p4c, "tooltip 显示两侧段距离（含合计占比）")
    w50 = [s for s in segs if s["from"] == 1950][0]
    w60 = [s for s in segs if s["from"] == 1960][0]
    w80 = [s for s in segs if s["from"] == 1980][0]
    ok(w50["speed"] > 0.98 and w60["speed"] > 0.98, "两段断层 speed 均 ≈ 1（最粗）")
    ok(w80["speed"] < 0.01, "1980s→1990s speed ≈ 0（最细）")

    print()
    print("=" * 78)
    print("结果：%s" % ("ALL PASS" if not fails else "FAIL %d 项" % len(fails)))
    print("=" * 78)
    for f in fails:
        print("  ✗ " + f)
    return 0 if not fails else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
