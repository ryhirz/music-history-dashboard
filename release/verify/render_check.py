# -*- coding: utf-8 -*-
"""Phase 3 渲染层验证（三宽度）：1440 / 900 / 478。

源码检查只能证明「代码写得像对的」。这一层把页面真正渲染出来，对**生成后的 DOM**
做几何与交互断言，覆盖三种布局分支（5/4 列 vs 2 列、字号与标题截断也不同）。

每宽度检查：
  A. 元素计数 —— 防「多组 selection 广播数据」类 bug
  B. 实线路径 d 与 Python 同公式重算逐项一致（容差 1e-6）→ 几何正确
  C. 10 条 1980s 参考线 x1 同值且等于重算值 → 「谷底对齐」成立
  D. 10 个面板 transform 与网格公式一致
  E. Hover：取**最后一格**做 21 点横扫
  F. 注解碰撞：抽 <text> 估包围盒（累积祖先 translate），重叠对必须为 0

release 版：EDGE / SRC / DB / WORK / PROFILE 全部相对定位；DB 缺失自动重建。
"""
import pathlib
import re
import subprocess
import sys
import html
import json
from urllib.parse import unquote

import paths

EDGE = paths.find_edge()
SRC = paths.HTML
DB = str(paths.DB)
WORK = paths.WORK / "probe"
PROFILE = paths.WORK / "edgeprofile"
WORK.mkdir(parents=True, exist_ok=True)

if not EDGE:
    sys.exit("FATAL: 找不到 msedge.exe —— 请用环境变量 WB_EDGE 指定")


def main() -> int:
    if not paths.ensure_db():
        print("FATAL: 数据库不可用，且重建失败")
        return 1
    src = SRC.read_text(encoding="utf-8")
    fails = []

    def chk(name, ok, detail=""):
        print(("    [PASS] " if ok else "    [FAIL] ") + name + (("  " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    import duckdb
    con = duckdb.connect(str(paths.DB), read_only=True)
    DB_ROWS = con.execute("""
    SELECT song_key, decade, n_versions, round(mean_acousticness,4),
           artist_low, artist_high, thin_cell
    FROM song_version_study_clean ORDER BY song_key, decade
    """).fetchall()
    N_ALL = len(DB_ROWS)
    N_THIN = sum(1 for r in DB_ROWS if r[6])
    con.close()

    CELL_RE = (r"\{ dec: (\d+), n: (\d+), mean: ([\d.]+), lo: ([\d.]+), hi: ([\d.]+), "
               r"loA: '((?:[^'\\]|\\.)*)', hiA: '((?:[^'\\]|\\.)*)', y0: (\d+), y1: (\d+), thin: (true|false) \}")
    SONG_RE = (r"\{ key: '((?:[^'\\]|\\.)*)', label: '((?:[^'\\]|\\.)*)', "
               r"vtot: (\d+), nd: (\d+), cells: \[(.*?)\n  \] \}")
    DECADES = [1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010]
    SVC = []
    for sm in re.finditer(SONG_RE, re.search(r"const SVC_SONGS = \[(.*?)\n\];", src, re.S).group(1), re.S):
        key, label, vtot, nd, cells = sm.groups()
        cs = []
        for cm in re.finditer(CELL_RE, cells):
            cs.append({"dec": int(cm.group(1)), "mean": float(cm.group(3)), "thin": cm.group(10) == "true"})
        SVC.append({"key": key, "label": label, "vtot": int(vtot), "cells": cs})

    PROBE = r"""
    <div id="__probe"></div>
    <script>
    (function(){
      var tries = 0;
      var t = setInterval(function(){
        var svg = document.querySelector('#chart-micro svg');
        var deep = document.querySelector('#chart-micro-deep svg');
        if (!svg || !deep){ if (++tries > 400) { clearInterval(t); dump(['TIMEOUT']); } return; }
        clearInterval(t);
        setTimeout(function(){ run(svg, deep); }, 3200);
      }, 100);
      function dump(lines){
        document.getElementById('__probe').setAttribute(
          'data-payload', lines.map(encodeURIComponent).join('\n'));
      }
      function run(svg, deep){
        var out = [];
        function N(sel, root){ return (root || svg).querySelectorAll(sel).length; }
        out.push('svgW=' + svg.getAttribute('width'));
        out.push('panels=' + N('g.sm'));
        out.push('solid=' + N('path.sm-solid'));
        out.push('dash=' + N('path.sm-dash'));
        out.push('dots=' + N('circle.sm-dot'));
        out.push('thindots=' + N('circle.sm-dot-thin'));
        out.push('rings=' + N('circle.sm-ring'));
        out.push('refs=' + N('line.sm-ref'));
        out.push('deepdots=' + N('circle[r="3.1"]', deep));

        var i;
        var dps = svg.querySelectorAll('path.sm-solid');
        for (i = 0; i < dps.length; i++) out.push('d' + i + '=' + (dps[i].getAttribute('d') || ''));
        var refx = {};
        var rl = svg.querySelectorAll('line.sm-ref');
        for (i = 0; i < rl.length; i++) refx[rl[i].getAttribute('x1')] = 1;
        out.push('refx=' + Object.keys(refx).join(','));
        var gs = svg.querySelectorAll('g.sm');
        for (i = 0; i < gs.length; i++) out.push('t' + i + '=' + gs[i].getAttribute('transform'));

        var rects = svg.querySelectorAll('g > rect[fill="transparent"]');
        var hitRect = rects[rects.length - 1];
        var svgRect = svg.getBoundingClientRect();
        var r = hitRect.getBoundingClientRect();
        var rx = parseFloat(rl[0].getAttribute('x1'));
        var tip = document.getElementById('tooltip');
        function fire(cx, cy){
          hitRect.dispatchEvent(new MouseEvent('mousemove',
            { bubbles: true, clientX: cx, clientY: cy, view: window }));
          var t2 = tip ? tip.textContent.replace(/\s+/g, ' ').trim() : '';
          var mm = t2.match(/(\d{4})s/);
          return mm ? mm[1] : '';
        }
        var cy = r.top + r.height / 2, scan = [], k;
        for (k = 0; k <= 20; k++) scan.push(fire(r.left + r.width * k / 20, cy));
        out.push('scan=' + scan.join(','));
        out.push('wantFrac=' + (rx / r.width).toFixed(4));
        out.push('lastXattr=' + hitRect.getAttribute('x'));
        out.push('svgLeft=' + svgRect.left.toFixed(2));
        out.push('rectLeft=' + r.left.toFixed(2));
        fire(r.left + rx, cy);
        out.push('tipText=' + (tip ? tip.textContent.replace(/\s+/g, ' ').trim() : ''));
        out.push('hoverMarkOn=' + svg.querySelectorAll('g > line[stroke="#9aa0a6"][opacity="0.55"]').length);
        dump(out);
      }
    })();
    </script>
    """

    CSS = """
    .page-head, footer { display: none !important; }
    main > section.panel:not(#sec-micro) { display: none !important; }
    body, .wrap { padding-top: 0 !important; }
    #sec-micro { margin: 0 !important; }
    """

    TAG_RE = re.compile(r"<(/?)([A-Za-z][\w:-]*)\b([^>]*?)(/?)>", re.S)
    ATTR_RE = re.compile(r"([\w:-]+)(?:\s*=\s*\"([^\"]*)\")?")

    def text_w(s, fs):
        def wide(ch):
            o = ord(ch)
            return (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF or 0xAC00 <= o <= 0xD7A3
                    or 0xF900 <= o <= 0xFAFF or 0xFE30 <= o <= 0xFE6F
                    or 0xFF00 <= o <= 0xFF60 or 0xFFE0 <= o <= 0xFFE6)
        return sum((1.0 if wide(c) else 0.55) for c in s) * fs

    def overlap_pairs(items, pad=1.0):
        hits = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if (a["x0"] < b["x1"] - pad and b["x0"] < a["x1"] - pad and
                        a["y0"] < b["y1"] - pad and b["y0"] < a["y1"] - pad):
                    hits.append("%s ⇄ %s" % (a["c"][:22], b["c"][:22]))
        return hits

    CIRC_RE = re.compile(r"<circle\b([^>]*)>", re.S)
    CONTAINERS = {"svg", "g", "defs", "clipPath", "marker"}
    LEAVES = {"text", "tspan", "circle", "path", "line", "rect", "title", "ellipse", "polygon"}

    def parse_svg(seg):
        texts, circles, stack = [], [], [(0.0, 0.0)]
        for m in TAG_RE.finditer(seg):
            closing, name, attrs, selfclose = (m.group(1), m.group(2).lower(), m.group(3), m.group(4))
            if name in CONTAINERS:
                if closing:
                    if len(stack) > 1:
                        stack.pop()
                elif not selfclose:
                    mm = re.search(r"translate\(\s*([-\d.eE]+)\s*[,\s]\s*([-\d.eE]+)", attrs)
                    dx, dy = (float(mm.group(1)), float(mm.group(2))) if mm else (0.0, 0.0)
                    px, py = stack[-1]
                    stack.append((px + dx, py + dy))
                continue
            if name not in LEAVES or closing or selfclose:
                continue
            a = dict((k, v if v is not None else "") for k, v in ATTR_RE.findall(attrs))
            bx, by = stack[-1]
            if name == "circle":
                try:
                    circles.append((bx + float(a.get("cx", 0)), by + float(a.get("cy", 0))))
                except ValueError:
                    pass
                continue
            if name == "text":
                body = seg[m.end():seg.find("</text>", m.end())]
                try:
                    lx, ly, fs = float(a.get("x", 0)), float(a.get("y", 0)), float(a.get("font-size", 11))
                except ValueError:
                    continue
                content = html.unescape(re.sub(r"<[^>]+>", "", body)).strip()
                if not content:
                    continue
                x, y = bx + lx, by + ly
                an = a.get("text-anchor", "start")
                w = text_w(content, fs)
                x0 = x if an == "start" else (x - w / 2 if an == "middle" else x - w)
                texts.append(dict(c=content, x0=x0, y0=y - fs * .78, x1=x0 + w, y1=y + fs * .22))
        return texts, circles

    def text_on_point(items, pts, m=2.0):
        hits = []
        for t in items:
            for cx, cy in pts:
                if (t["x0"] + m < cx < t["x1"] - m) and (t["y0"] + m < cy < t["y1"] - m):
                    hits.append("「%s」压住数据点(%.0f,%.0f)" % (t["c"][:20], cx, cy))
        return hits

    NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

    def nums(s):
        return [float(x) for x in NUM.findall(s or "")]

    def slice_svg(dom, div_id):
        i = dom.find('id="%s"' % div_id)
        if i < 0:
            return ""
        j = dom.find("</svg>", i)
        seg = dom[i:j]
        return seg[seg.find("<svg"):]

    def num(v):
        s = ("%.6f" % v).rstrip("0").rstrip(".")
        return s if s else "0"

    WIDTHS = [(1440, 2900), (900, 3400), (478, 5200)]
    for W_CAP, H_CAP in WIDTHS:
        print("=" * 100)
        print("▶ 宽度 %d    （窗口 %d×%d）" % (W_CAP, W_CAP, H_CAP))
        print("=" * 100)
        html_src = src.replace("</head>", "<style>%s</style>\n</head>" % CSS, 1)
        html_src = html_src.replace("</body>", PROBE + "\n</body>", 1)
        hp = WORK / ("r%d.html" % W_CAP)
        hp.write_text(html_src, encoding="utf-8")
        r = subprocess.run([
            EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--force-device-scale-factor=1", "--virtual-time-budget=20000",
            "--user-data-dir=" + str(PROFILE),
            "--window-size=%d,%d" % (W_CAP, H_CAP), "--dump-dom", hp.as_uri(),
        ], capture_output=True, text=True, timeout=240)
        dom = r.stdout
        (WORK / ("dom_%d.html" % W_CAP)).write_text(dom, encoding="utf-8")
        mm = re.search(r"<div id=\"__probe\" data-payload=\"([^\"]*)\"", dom)
        if not mm:
            chk("探针回填 payload", False, "页面可能没渲染出来")
            continue
        kv = {}
        for ln in [unquote(x) for x in mm.group(1).split("\n")]:
            if "=" in ln:
                k, v = ln.split("=", 1)
                kv[k] = v

        print("  A. 元素计数")
        for label, key, exp in [
            ("面板 10", "panels", 10), ("实线路径 10", "solid", 10), ("虚线路径 10", "dash", 10),
            ("实心点 = %d" % (N_ALL - N_THIN), "dots", N_ALL - N_THIN),
            ("空心点 = %d" % N_THIN, "thindots", N_THIN),
            ("谷底环 10", "rings", 10), ("参考线 10", "refs", 10), ("深潜散点 44", "deepdots", 44),
        ]:
            chk(label, int(kv.get(key, -1)) == exp, "实际 %s" % kv.get(key))

        W = float(kv["svgW"])
        cols = 5 if W >= 1180 else (4 if W >= 900 else (3 if W >= 620 else 2))
        rows = -(-10 // cols)
        gap = 8 if W < 520 else 12
        ph = 78 if W < 520 else (86 if W < 900 else 94)
        M = {"top": 12, "right": 8, "bottom": 42 if W < 520 else 34, "left": 28 if W < 520 else 36}
        pw = (W - M["left"] - M["right"] - gap * (cols - 1)) / cols
        PT, FB = 18, 14
        plotH = ph - PT - FB
        PAD = 0.42
        step = pw / (len(DECADES) - 1 + 2 * PAD)
        X = {d: step * (i + PAD) for i, d in enumerate(DECADES)}

        def seg_path(song, want_dash):
            d = ""
            for i in range(len(DECADES) - 1):
                a = next((c for c in song["cells"] if c["dec"] == DECADES[i]), None)
                b = next((c for c in song["cells"] if c["dec"] == DECADES[i + 1]), None)
                if not a or not b or (a["thin"] or b["thin"]) != want_dash:
                    continue
                d += "M%s,%sL%s,%s" % (num(X[DECADES[i]]), num(plotH - a["mean"] * plotH),
                                       num(X[DECADES[i + 1]]), num(plotH - b["mean"] * plotH))
            return d

        print("  B. 实线路径几何（Python 重算比对）")
        bad = []
        for i, s in enumerate(SVC):
            a, b = nums(seg_path(s, False)), nums(kv.get("d%d" % i, ""))
            if len(a) != len(b) or any(abs(x - y) > 1e-6 for x, y in zip(a, b)):
                bad.append(s["key"])
        chk("10 条实线路径 d 逐项一致", not bad, "不符：%s" % (bad or "无"))

        print("  C. 1980s 谷底对齐")
        refx = kv.get("refx", "")
        ok_ref = refx != "" and "," not in refx and abs(float(refx) - X[1980]) < 1e-6
        chk("10 条参考线 x1 同值 = 重算 x(1980)", ok_ref, "x1=%s  重算=%.4f" % (refx, X[1980]))

        print("  D. 面板网格")
        gb = []
        for i in range(10):
            exp = (M["left"] + (i % cols) * (pw + gap), M["top"] + (i // cols) * (ph + gap))
            got = nums(kv.get("t%d" % i, ""))
            if len(got) != 2 or abs(got[0] - exp[0]) > 1e-6 or abs(got[1] - exp[1]) > 1e-6:
                gb.append("格%d 期望(%.4f,%.4f) 实际%s" % (i, exp[0], exp[1], got))
        chk("10 个面板 transform 一致", not gb,
            ("%d 列 × %d 行；" % (cols, rows)) + ("；".join(gb[:2]) if gb else "全部吻合"))

        print("  E. Hover 横扫（最后一格 = 最右列，偏移最大）")
        scan = [x for x in kv.get("scan", "").split(",") if x]
        want_frac = float(kv.get("wantFrac", "0"))
        want_idx = round(want_frac * 20)
        chk("21 点全部有吸附结果", len(scan) == 21, "实际 %d" % len(scan))
        if len(scan) == 21:
            chk("左端 = 1930s", scan[0] == "1930", scan[0])
            chk("右端 = 2010s", scan[-1] == "2010", scan[-1])
            chk("十年单调不减（无错位跳变）",
                all(int(scan[i + 1]) >= int(scan[i]) for i in range(20)), " ".join(scan))
            chk("x(1980) 处吸附到 1980s", scan[want_idx] == "1980",
                "第 %d 点 = %s   （横扫：%s）" % (want_idx, scan[want_idx], " ".join(scan)))
        chk("hover 标记线高亮 1 条", int(kv.get("hoverMarkOn", -1)) == 1, kv.get("hoverMarkOn"))
        tip = kv.get("tipText", "")
        chk("tooltip 有内容", len(tip) > 40, tip[:80])

        print("  F. 注解碰撞（<text> 包围盒 × 文字 / × 数据点）")
        seg_sm = slice_svg(dom, "chart-micro")
        seg_dp = slice_svg(dom, "chart-micro-deep")
        tx_sm, _ = parse_svg(seg_sm)
        tx_dp, ci_dp = parse_svg(seg_dp)
        ov = overlap_pairs(tx_sm) + overlap_pairs(tx_dp)
        chk("两张图「文字×文字」零重叠", not ov, "；".join(ov[:4]) if ov else "小多图 + 深潜均无重叠")
        onpt = text_on_point(tx_dp, ci_dp)
        chk("深潜图「文字×数据点」零压盖（%d 个点）" % len(ci_dp), not onpt,
            "；".join(onpt[:4]) if onpt else "无文字压住散点")
        print()

    print("=" * 100)
    print("总判定：%s（失败 %d 项，三宽度 × 六类断言）" % ("ALL PASS" if not fails else "HAS FAILURE", len(fails)))
    if fails:
        for f in fails:
            print("  ✗ " + f)
    print("=" * 100)
    return 0 if not fails else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
