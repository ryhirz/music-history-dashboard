# -*- coding: utf-8 -*-
"""Phase 3 前端校验：内联 JS 语法 + 数据逐值比对 + 文案数字核对 + 结构检查

release 版：HTML / DB / NODE 全部通过 paths 相对定位；DB 缺失时自动重建。
"""
import re
import pathlib
import subprocess
import sys
import tempfile
import duckdb

import paths

HTML = paths.HTML
NODE = paths.node()
DB = paths.DB


def main() -> int:
    if not HTML.exists():
        print("FATAL: 看板缺失 -> %s" % HTML)
        return 1
    if not paths.ensure_db():
        print("FATAL: 数据库不可用，且重建失败")
        return 1

    src = HTML.read_text(encoding="utf-8")
    fails = []

    def chk(name, ok, detail=""):
        print(("  [PASS] " if ok else "  [FAIL] ") + name + (("  " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    print("=" * 100)
    print("1. 内联 JS 语法检查（node --check）")
    print("=" * 100)
    blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", src, re.S)
    print("  找到内联 script 块 = %d" % len(blocks))
    for i, b in enumerate(blocks):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(b)
            p = f.name
        r = subprocess.run([NODE, "--check", p], capture_output=True, text=True)
        ok = r.returncode == 0
        chk("script 块 %d（%d 字符）" % (i + 1, len(b)), ok)
        if not ok:
            print((r.stderr or "")[:1200])

    print()
    print("=" * 100)
    print("2. SVC_SONGS 与锁定视图逐值比对（81 格 × 9 字段）")
    print("=" * 100)
    CELL_RE = (r"\{ dec: (\d+), n: (\d+), mean: ([\d.]+), lo: ([\d.]+), hi: ([\d.]+), "
               r"loA: '((?:[^'\\]|\\.)*)', hiA: '((?:[^'\\]|\\.)*)', y0: (\d+), y1: (\d+), thin: (true|false) \}")
    SONG_RE = (r"\{ key: '((?:[^'\\]|\\.)*)', label: '((?:[^'\\]|\\.)*)', "
               r"vtot: (\d+), nd: (\d+), cells: \[(.*?)\n  \] \}")

    m = re.search(r"const SVC_SONGS = \[(.*?)\n\];", src, re.S)
    songs = []
    for sm in re.finditer(SONG_RE, m.group(1), re.S):
        key, label, vtot, nd, cells = sm.groups()
        cs = []
        for cm in re.finditer(CELL_RE, cells):
            cs.append({"dec": int(cm.group(1)), "n": int(cm.group(2)),
                       "mean": float(cm.group(3)), "lo": float(cm.group(4)), "hi": float(cm.group(5)),
                       "loA": cm.group(6).replace("\\'", "'"), "hiA": cm.group(7).replace("\\'", "'"),
                       "y0": int(cm.group(8)), "y1": int(cm.group(9)), "thin": cm.group(10) == "true"})
        songs.append({"key": key.replace("\\'", "'"), "label": label, "vtot": int(vtot),
                      "nd": int(nd), "cells": cs})

    n_cells = sum(len(s["cells"]) for s in songs)
    chk("解析曲目数 = 10", len(songs) == 10, "实际 %d" % len(songs))
    chk("解析格子数 = 81", n_cells == 81, "实际 %d" % n_cells)

    con = duckdb.connect(str(DB), read_only=True)
    db = con.execute("""
    SELECT song_key, decade, n_versions,
           round(mean_acousticness,4), round(min_acousticness,4), round(max_acousticness,4),
           artist_low, artist_high, year_min, year_max, thin_cell, n_versions_total
    FROM song_version_study_clean ORDER BY song_key, decade
    """).fetchall()
    chk("库内视图行数 = 81", len(db) == 81, "实际 %d" % len(db))

    idx = {(r[0], r[1]): r for r in db}
    mis = []
    for s in songs:
        for c in s["cells"]:
            r = idx.get((s["key"], c["dec"]))
            if r is None:
                mis.append("%s@%d 库中不存在" % (s["key"], c["dec"]))
                continue
            exp = {"n": r[2], "mean": r[3], "lo": r[4], "hi": r[5],
                   "loA": r[6], "hiA": r[7], "y0": r[8], "y1": r[9], "thin": bool(r[10])}
            for k, v in exp.items():
                if c[k] != v:
                    mis.append("%s@%d %s: 看板=%r 库=%r" % (s["key"], c["dec"], k, c[k], v))
        vtot_db = int(idx[(s["key"], s["cells"][0]["dec"])][11])
        if s["vtot"] != vtot_db:
            mis.append("%s vtot: 看板=%s 库=%s" % (s["key"], s["vtot"], vtot_db))
    chk("81 格 × 9 字段 + vtot 逐值一致", len(mis) == 0,
        ("前 6 条：" + " | ".join(mis[:6])) if mis else "0 处不符")

    print()
    print("=" * 100)
    print("3. SVC_POOLED 与视图聚合比对")
    print("=" * 100)
    mp = re.search(r"const SVC_POOLED = \[(.*?)\n\];", src, re.S)
    pooled_js = [(int(g[0]), float(g[1]), float(g[2]), int(g[3]), int(g[4])) for g in (
        m.groups() for m in re.finditer(
            r"\{ dec: (\d+), eq: ([\d.]+), wt: ([\d.]+), n: (\d+), k: (\d+) \}", mp.group(1)))]
    pooled_db = con.execute("""
    SELECT decade, round(avg(mean_acousticness),4),
           round(sum(n_versions*mean_acousticness)/sum(n_versions),4), sum(n_versions), count(*)
    FROM song_version_study_clean GROUP BY 1 ORDER BY 1
    """).fetchall()
    chk("池化十年数 = 9", len(pooled_js) == len(pooled_db) == 9, "%d vs %d" % (len(pooled_js), len(pooled_db)))
    pm = ["%r vs %r" % (a, b) for a, b in zip(pooled_js, pooled_db) if a != b]
    chk("池化数值逐值一致", len(pm) == 0, " | ".join(pm) if pm else "0 处不符")
    pooled_n = [a for a in pooled_js if a[0] == 1980][0]
    chk("1980s 为池化最低（等权与加权同向）",
        pooled_n[1] == min(p[1] for p in pooled_js) and pooled_n[2] == min(p[2] for p in pooled_js),
        "等权 %.4f / 加权 %.4f" % (pooled_n[1], pooled_n[2]))

    print()
    print("=" * 100)
    print("4. Silent Night 行级明细（44 条）与库比对")
    print("=" * 100)
    ms = re.search(r"const SLN_RECORDS = \[(.*?)\n\];", src, re.S)
    recs_js = [{"y": int(g[0]), "a": g[1].replace("\\'", "'"), "ac": float(g[2])} for g in (
        m.groups() for m in re.finditer(
            r"\{ y: (\d+), a: '((?:[^'\\]|\\.)*)', ac: ([\d.]+) \}", ms.group(1)))]
    chk("解析 44 条", len(recs_js) == 44, "实际 %d" % len(recs_js))
    recs_db = con.execute("""
    WITH raw_pool AS (
        SELECT artists, year, id, duration_ms, acousticness FROM raw_tracks
        WHERE year IS NOT NULL AND name IS NOT NULL AND lower(trim(name)) = 'silent night'
    ),
    clean AS (
        SELECT * FROM (SELECT r.*, row_number() OVER (PARTITION BY r.artists, r.duration_ms
                       ORDER BY r.year, r.id) AS rn FROM raw_pool r WHERE r.year >= 1818) WHERE rn = 1)
    SELECT year, trim(replace(split_part(artists, ',', 1), '[', ''), ' ''"[]') AS artist, round(acousticness,4)
    FROM clean ORDER BY year, artist, acousticness
    """).fetchall()
    rm = ["%r vs %r" % (a, b) for a, b in zip(recs_js, recs_db)
          if (a["y"], a["a"], a["ac"]) != (b[0], b[1], b[2])]
    chk("44 条逐值一致（按位）", len(rm) == 0, " | ".join(rm[:4]) if rm else "0 处不符")
    js_ms = sorted((r["y"], r["a"], r["ac"]) for r in recs_js)
    db_ms = sorted((b[0], b[1], float(b[2])) for b in recs_db)
    chk("44 条多重集相等（次序无关）", js_ms == db_ms,
        "仅次序不同" if js_ms == db_ms else "集合本身不一致")

    lo = min(recs_js, key=lambda r: r["ac"])
    chk("谷底 = Bon Jovi 1985 @ 0.0914", (lo["y"], lo["a"], lo["ac"]) == (1985, "Bon Jovi", 0.0914),
        "%r" % lo)
    c10 = [c for s in songs if s["key"] == "silent night" for c in s["cells"] if c["dec"] == 2010][0]
    chk("复兴峰 = Michael Bublé 2011 @ 0.9590",
        c10["hiA"] == "Michael Bublé" and c10["hi"] == 0.959, "%r" % c10["hiA"])
    delta = c10["hi"] - lo["ac"]
    chk("Δ = 0.868（文案一致）", abs(delta - 0.868) < 5e-4, "%.4f" % delta)

    print()
    print("=" * 100)
    print("5. 文案数字核对")
    print("=" * 100)
    TXT = [
        ("ICC 0.64", "ICC <b>0.64</b>"), ("ICC 0.17", "ICC <b>0.17</b>"),
        ("谷底 0.6136", "0.6136"), ("1950s 0.8017", "0.8017"),
        ("Δ +0.868", "+0.868"), ("谷底 0.091", "<code>0.091</code>"),
        ("峰值 0.959", "<code>0.959</code>"), ("44 条", "44 条"),
        ("436 条版本记录", "436 条版本记录"), ("647 行 / 15 首", "647 行 / 15 首"),
        ("457 行 / 10 首", "457 行 / 10 首"), ("445 行", "445 行"),
        ("16 条物理不可能", "16 条物理不可能"), ("81 个格子", "81 个格子"),
        ("19 个格子", "19 个格子"), ("ICC 修正说明", "ICC(1,1)"),
        ("旧口径溯源", "0.88 / 0.49"), ("k̄ 口径说明", "k̄"),
    ]
    for label, needle in TXT:
        chk("文案含 " + label, needle in src)

    print()
    print("=" * 100)
    print("6. 结构检查")
    print("=" * 100)
    code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    code = re.sub(r"(?m)//[^\n]*", "", code)

    STRUCT = [
        ("#sec-micro 已实现（非 placeholder）", 'id="sec-micro" class="panel"' in src),
        ("#chart-micro 容器", 'id="chart-micro"' in src),
        ("#chart-micro-deep 容器", 'id="chart-micro-deep"' in src),
        ("ICC 金句块", 'id="micro-quote"' in src),
        ("SVC_SONGS / SVC_POOLED / SLN_RECORDS 三数据块",
         all(k in src for k in ("const SVC_SONGS = [", "const SVC_POOLED = [", "const SLN_RECORDS = ["))),
        ("renderMicro 定义", "function renderMicro(){" in src),
        ("renderMicroDeep 定义", "function renderMicroDeep(){" in src),
        ("showTipMicro 定义", "function showTipMicro(" in src),
        ("placeTooltip 定义", "function placeTooltip(" in src),
        ("两图均被调用", "renderMicro();" in src and "renderMicroDeep();" in src),
        ("全部 loading 占位均被移除（6 个 loading 节点）",
         src.count("if (loadingEl) loadingEl.remove();") == 6),
        ("ResizeObserver 表驱动", "const targets = [" in src),
        ("fallback 覆盖全部 7 个容器",
         "[macroEl, mesoEl, mesoShapeEl, microEl, microDeepEl, spaceEl, spaceCorrEl]" in src),
        ("footer 已升到 Phase 5", "D3 看板 Phase 5" in src),
        ("无残留数据块占位标记", "__SVC_DATA_BLOCK__" not in src),
        ("无 d3.pointer(ev, selection) 误用", "d3.pointer(ev, g)" not in code),
        ("无 d3.pointer(ev, this) 误用（带 x/y 的元素自指会解成 SVG 根坐标）",
         "d3.pointer(ev, this)" not in code),
        ("小多图 hover 走 svg 根坐标 + 手工减面板偏移",
         "d3.pointer(ev, svg.node())" in code and "const mx = px - panelL;" in code),
        ("小多图无「多组 selection 广播数据」写法（.data(SVC_SONGS) 仅 1 处合法）",
         code.count(".data(SVC_SONGS)") == 1),
        ("小多图用嵌套 join 父级数据形式 .data(d => [d])",
         code.count(".data(d => [d])") >= 2),
        ("#sec-space 已从 placeholder 升级为正式区块",
         'id="sec-space" class="panel"' in src
         and 'id="sec-space" class="panel placeholder"' not in src),
        ("#sec-space 两个图表容器就位",
         'id="chart-space"' in src and 'id="chart-space-corr"' in src),
    ]
    for label, ok in STRUCT:
        chk(label, ok)

    print()
    print("=" * 100)
    print("总判定：%s（失败 %d 项）" % ("ALL PASS" if not fails else "HAS FAILURE", len(fails)))
    print("=" * 100)
    con.close()
    return 0 if not fails else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
