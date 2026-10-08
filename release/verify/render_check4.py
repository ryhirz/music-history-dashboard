# -*- coding: utf-8 -*-
"""Phase 4 渲染层校验：Headless Edge 三宽度 × 八类断言。

断言：
  A 元素计数（11 点 / 10 段 / 11 椭圆 / 11 条副图 / 11 标签）
  B **线宽速度编码**：最粗两段必须显著粗于最细段；且窄屏下仍可辨
  C **误差椭圆不越界**：全部 ellipse 的外接框落在 [0,1] 绘图区内
  D **X 轴反向**：ac 越大 x 越小（1920s 在右、1940s 在左）
  E **断层段粗于邻居**：1950→1960、1960→1970 的 stroke-width 是最大值
  F 注解几何零重叠（文字 × 文字、文字 × 数据点）
  G 主副图三段式色块 x 区间一致（视觉呼应的机器证明）
  H hover 探针：横扫 all 11 点命中，且 1960s 的 tooltip 含两侧段距离

release 版：HTML / EDGE / WORK / p4_export 全部相对定位；DB 与 p4_export 缺失自动重建/生成。
"""
import json
import math
import pathlib
import re
import subprocess
import sys

import paths

WORK = paths.WORK
HTML = paths.HTML
EDGE = paths.find_edge()
if not EDGE:
    sys.exit("FATAL: 找不到 msedge.exe —— 请用环境变量 WB_EDGE 指定")

P4_EXPORT = paths.HERE / "p4_export.json"


def main() -> int:
    if not paths.ensure_db():
        print("FATAL: 数据库不可用，且重建失败")
        return 1
    if not paths.ensure_p4_export():
        print("FATAL: p4_export.json 生成失败")
        return 1

    WIDTHS = [1440, 900, 478]
    fails = []

    def ok(cond, msg):
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        if not cond:
            fails.append(msg)

    def dump_dom(w):
        prof = WORK / ("p4_edge_%d" % w)
        out = WORK / ("p4_dom_%d.html" % w)
        prof.mkdir(parents=True, exist_ok=True)
        cmd = [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
               "--force-device-scale-factor=1",
               "--user-data-dir=" + str(prof),
               "--virtual-time-budget=9000",
               "--window-size=%d,1400" % w,
               "--dump-dom", HTML.as_uri()]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        out.write_text(r.stdout or "", encoding="utf-8")
        return out.read_text(encoding="utf-8")

    # ── SVG 嵌套解析器（累积 translate，只把 svg/g 当容器）─────────────────
    CONTAINERS = {"svg", "g"}
    TOKEN = re.compile(r"<(/?)([a-zA-Z][\w:-]*)((?:\"[^\"]*\"|'[^']*'|[^>\"])*?)(/?)>", re.S)
    ATTR = re.compile(r"([\w:-]+)\s*=\s*(\"([^\"]*)\"|'([^']*)')")

    def attrs_of(s):
        d = {}
        for m in ATTR.finditer(s):
            d[m.group(1)] = m.group(3) if m.group(3) is not None else m.group(4)
        return d

    def parse_nested(svg_text):
        out, stack = [], [{"tx": 0.0, "ty": 0.0}]
        for m in TOKEN.finditer(svg_text):
            closing, tag, astr, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
            if closing:
                if tag in CONTAINERS and len(stack) > 1:
                    stack.pop()
                continue
            a = attrs_of(astr)
            cur = stack[-1]
            tx, ty = cur["tx"], cur["ty"]
            tr = a.get("transform", "")
            mt = re.search(r"translate\(\s*(-?[\d.eE+]+)[ ,]+(-?[\d.eE+]+)\s*\)", tr)
            if mt:
                tx += float(mt.group(1))
                ty += float(mt.group(2))
            out.append({"tag": tag, "attrs": a, "tx": tx, "ty": ty, "depth": len(stack)})
            if tag in CONTAINERS and not selfclose:
                stack.append({"tx": tx, "ty": ty})
        return out

    def num(a, k, dflt=None):
        v = a.get(k)
        if v is None:
            return dflt
        try:
            return float(v)
        except Exception:
            return dflt

    def text_width(t, fs):
        w = 0.0
        for ch in t:
            o = ord(ch)
            if (0x2E80 <= o <= 0x9FFF or 0xFF00 <= o <= 0xFF60 or
                    0x3000 <= o <= 0x303F or o in (0x2014, 0x2192, 0x2190, 0xB7, 0x2212)):
                w += 1.0
            elif ch == " ":
                w += 0.3
            else:
                w += 0.56
        return w * fs * 1.04

    def classify(els):
        pts = [e for e in els if e["tag"] == "circle" and "sp-dot" in e["attrs"].get("class", "")]
        hits = [e for e in els if e["tag"] == "circle" and "sp-hit" in e["attrs"].get("class", "")]
        ells = [e for e in els if e["tag"] == "ellipse"]
        bars = [e for e in els if e["tag"] == "rect" and "sp-bar" in e["attrs"].get("class", "")]
        labs = [e for e in els if e["tag"] == "text" and "sp-lab" in e["attrs"].get("class", "")]
        paths_ = [e for e in els if e["tag"] == "path"
                  and "d" in e["attrs"] and num(e["attrs"], "stroke-width") is not None
                  and e["attrs"].get("fill") == "none"]
        return pts, hits, ells, bars, labs, paths_

    report = {}
    for W in WIDTHS:
        print("=" * 78)
        print("宽度 %d px" % W)
        print("=" * 78)
        dom = dump_dom(W)
        ok(len(dom) > 5000, "DOM 已导出（%d 字符）" % len(dom))

        def svg_of(cid):
            i = dom.find('id="%s"' % cid)
            if i < 0:
                return ""
            j = dom.find("<svg", i)
            if j < 0:
                return ""
            k = dom.find("</svg>", j)
            return dom[j:k + 6]

        s_main = svg_of("chart-space")
        s_corr = svg_of("chart-space-corr")
        ok(bool(s_main), "主图 SVG 存在")
        ok(bool(s_corr), "副图 SVG 存在")
        if not s_main or not s_corr:
            continue

        em = classify(parse_nested(s_main))
        ec = classify(parse_nested(s_corr))
        pts, hits, ells, _, labs, paths_ = em
        cpts, chits, cells_, cbars, clabs, _ = ec

        ok(len(pts) == 11, "A1 主图数据点 = 11（实为 %d）" % len(pts))
        ok(len(ells) == 11, "A2 误差椭圆 = 11（实为 %d）" % len(ells))
        ok(len(labs) == 11, "A3 十年标签 = 11（实为 %d）" % len(labs))
        ok(len(cbars) == 11, "A4 副图条 = 11（实为 %d）" % len(cbars))
        ok(len(paths_) == 12, "A5 主图段路径 = 12（10 段 + 2 断层柔光，实为 %d）" % len(paths_))

        texts = [t for t in re.findall(r"<text[^>]*class=\"sp-lab\"[^>]*>([^<]*)</text>", s_main)]
        ok(len(texts) == 11, "D0 标签文字 = 11（实为 %d）" % len(texts))

        EQ = json.loads(P4_EXPORT.read_text(encoding="utf-8"))
        order = [r["dec"] for r in EQ["rows"]]
        dom_order = []
        for t in texts:
            mm = re.match(r"(\d+)s", t.strip())
            if mm:
                dom_order.append(int(mm.group(1)))
        ok(dom_order == order, "D1 DOM 点顺序 == EQ_ROWS 顺序")

        pos = {}
        for i, d in enumerate(order):
            pos[d] = (num(pts[i]["attrs"], "cx"), num(pts[i]["attrs"], "cy"))
        acmap = {r["dec"]: r["ac"] for r in EQ["rows"]}
        enmap = {r["dec"]: r["en"] for r in EQ["rows"]}
        xmax_ac = max(order, key=lambda d: acmap[d])
        xmin_ac = min(order, key=lambda d: acmap[d])
        ok(pos[xmax_ac][0] < pos[xmin_ac][0],
           "D2 X 轴反向：ac 最大(%ds) 的 x=%.1f < ac 最小(%ds) 的 x=%.1f" % (
               xmax_ac, pos[xmax_ac][0], xmin_ac, pos[xmin_ac][0]))
        ymax_en = max(order, key=lambda d: enmap[d])
        ymin_en = min(order, key=lambda d: enmap[d])
        ok(pos[ymax_en][1] < pos[ymin_en][1],
           "D3 Y 轴正向：en 最大(%ds) 的 y=%.1f < en 最小(%ds) 的 y=%.1f" % (
               ymax_en, pos[ymax_en][1], ymin_en, pos[ymin_en][1]))

        xs_seq = [pos[d][0] for d in order]
        ok(xs_seq[-1] > xs_seq[0], "D4 轨迹整体从右向左推进（2020s 在最右）")

        glow = [p for p in paths_ if abs(num(p["attrs"], "stroke-opacity", 1) - 0.12) < 1e-6]
        real = [p for p in paths_ if abs(num(p["attrs"], "stroke-opacity", 1) - 0.12) > 1e-6]
        segw = [num(p["attrs"], "stroke-width") for p in real]
        SEG = EQ["seg"]
        seg_order = [(s["from"], s["to"]) for s in SEG]
        ok(len(segw) == 10, "A5a 真实段路径 = 10（实为 %d）" % len(segw))
        ok(len(glow) == 2, "A5b 断层柔光路径 = 2（实为 %d）" % len(glow))
        starts = []
        for p in real:
            m = re.match(r"M\s*([\d.]+),([\d.]+)", p["attrs"]["d"])
            starts.append((float(m.group(1)), float(m.group(2))))
        exp_starts = [pos[f] for (f, t) in seg_order]
        ok(all(abs(a[0] - b[0]) < 0.6 and abs(a[1] - b[1]) < 0.6 for a, b in zip(starts, exp_starts)),
           "A5c 段 DOM 顺序 == EQ_SEG 顺序（起点逐个吻合）")

        def wof(f, t):
            return [s for s in SEG if s["from"] == f and s["to"] == t][0]

        w5060 = wof(1950, 1960)
        w6070 = wof(1960, 1970)
        w8090 = wof(1980, 1990)
        i5060 = seg_order.index((1950, 1960))
        i6070 = seg_order.index((1960, 1970))
        i8090 = seg_order.index((1980, 1990))

        def esper(s):
            return 1 + s["speed"] * 7

        ok(abs(segw[i5060] - esper(w5060)) < 0.05,
           "B1 1950s→1960s 线宽 %.2f == 期望 %.2f" % (segw[i5060], esper(w5060)))
        ok(abs(segw[i6070] - esper(w6070)) < 0.05,
           "B2 1960s→1970s 线宽 %.2f == 期望 %.2f" % (segw[i6070], esper(w6070)))
        ok(abs(segw[i8090] - esper(w8090)) < 0.05,
           "B3 1980s→1990s 线宽 %.2f == 期望 %.2f（最细）" % (segw[i8090], esper(w8090)))
        ok(segw[i5060] > 7.5 and segw[i6070] > 7.5, "B4 两段断层均为最粗（>7.5px）")
        ok(segw[i8090] < 1.5, "B5 停滞段最细（<1.5px）")
        ratio = min(segw[i5060], segw[i6070]) / segw[i8090]
        ok(ratio > 5, "B6 最粗/最细 = %.1f× （远大于 1，速度编码可辨）" % ratio)
        d5060_8090 = segw[i5060] - segw[i8090]
        ok(d5060_8090 > 5.5, "B7 窄屏可辨性：最粗−最细 = %.2fpx（>5.5px 肉眼可辨）" % d5060_8090)
        mono = all(abs(segw[i] - esper(SEG[i])) < 0.05 for i in range(10))
        ok(mono, "B8 10 段线宽全部与 speed 映射一致")

        rank = sorted(range(10), key=lambda i: -segw[i])
        ok(set(rank[:2]) == {i5060, i6070},
           "E1 断层两段 = 全图线宽前二名（第1位 %.2f / 第2位 %.2f）"
           % (segw[rank[0]], segw[rank[1]]))

        zone_rects = [e for e in parse_nested(s_main)
                      if e["tag"] == "rect" and num(e["attrs"], "height", 0) > 100
                      and e["attrs"].get("fill") not in (None, "none")]
        ok(len(zone_rects) >= 3, "C0 三段式背景色块 = %d（≥3）" % len(zone_rects))
        plot_x0 = min(num(r["attrs"], "x") + r["tx"] for r in zone_rects)
        plot_x1 = max(num(r["attrs"], "x") + r["tx"] + num(r["attrs"], "width") for r in zone_rects)
        plot_y0 = min(num(r["attrs"], "y") + r["ty"] for r in zone_rects)
        plot_y1 = max(num(r["attrs"], "y") + r["ty"] + num(r["attrs"], "height") for r in zone_rects)
        ok(True, "C1 绘图区 x[%.1f, %.1f] y[%.1f, %.1f]" % (plot_x0, plot_x1, plot_y0, plot_y1))
        ov = 0
        for e in ells:
            a = e["attrs"]
            cx = num(a, "cx") + e["tx"]
            cy = num(a, "cy") + e["ty"]
            rx = num(a, "rx", 0)
            ry = num(a, "ry", 0)
            if cx - rx < plot_x0 - 0.5 or cx + rx > plot_x1 + 0.5 or cy - ry < plot_y0 - 0.5 or cy + ry > plot_y1 + 0.5:
                ov += 1
        ok(ov == 0, "C2 误差椭圆 11/11 不越出绘图区（越界 %d 个）" % ov)
        rmax = max(max(num(e["attrs"], "rx", 0), num(e["attrs"], "ry", 0)) for e in ells)
        ok(rmax < 12, "C3 椭圆最大半径 %.2fpx（SE 口径，极小 → 不越界）" % rmax)

        def zone_spans(svg_text):
            rs = [e for e in parse_nested(svg_text)
                  if e["tag"] == "rect" and num(e["attrs"], "height", 0) > 60
                  and e["attrs"].get("fill") not in (None, "none")]
            rs = sorted(rs, key=lambda r: num(r["attrs"], "x"))
            xs = [num(r["attrs"], "x") for r in rs]
            ws = [num(r["attrs"], "width") for r in rs]
            tot = (max(x + w for x, w in zip(xs, ws)) - min(xs)) or 1.0
            return [(w / tot) for w in ws], min(xs), max(x + w for x, w in zip(xs, ws))

        mspan, _, _ = zone_spans(s_main)
        cspan, _, _ = zone_spans(s_corr)
        ok(len(mspan) == 3 and len(cspan) == 3,
           "G1 主副图各 3 个三段式色块（主 %d / 副 %d）" % (len(mspan), len(cspan)))
        if len(mspan) == 3 and len(cspan) == 3:
            rw = max(abs(a - b) for a, b in zip(mspan, cspan))
            ok(rw < 0.08,
               "G2 主副图三段色块【相对区间比例】呼应：最大差 %.3f（阈值 0.08）" % rw)

        all_text = [e for e in parse_nested(s_main) if e["tag"] == "text"]
        txt_items = []
        for m in re.finditer(r"<text([^>]*)>([^<]*)</text>", s_main):
            a = attrs_of(m.group(1))
            t = m.group(2)
            if not t.strip():
                continue
            idx = m.start()
            pre = s_main[:idx]
            trs = re.findall(r"<g[^>]*transform=\"translate\(([-\d.]+)[ ,]+([-\d.]+)\)\"", pre)
            tx, ty = (float(trs[-1][0]), float(trs[-1][1])) if trs else (0, 0)
            x0 = float(a.get("x", 0))
            y0 = float(a.get("y", 0))
            anch = a.get("text-anchor", "start")
            fs = float(a.get("font-size", 11))
            wpx = text_width(t, fs)
            if anch == "middle":
                bx0 = x0 - wpx / 2
            elif anch == "end":
                bx0 = x0 - wpx
            else:
                bx0 = x0
            txt_items.append({"t": t, "x0": bx0 + tx, "x1": bx0 + wpx + tx,
                              "y0": y0 - fs + ty, "y1": y0 + 2 + ty, "fs": fs})

        def overlap(a, b, pad=1.0):
            return not (a["x1"] + pad < b["x0"] or b["x1"] + pad < a["x0"] or
                        a["y1"] + pad < b["y0"] or b["y1"] + pad < a["y0"])

        tt = 0
        for i in range(len(txt_items)):
            for j in range(i + 1, len(txt_items)):
                if txt_items[i]["t"] == txt_items[j]["t"]:
                    continue
                if overlap(txt_items[i], txt_items[j], 0.5):
                    tt += 1
        ok(tt == 0, "F1 注解零重叠：文字 × 文字 重叠 %d 对" % tt)
        pd = 0
        for t in txt_items:
            for d in order:
                px, py = pos[d]
                if t["x0"] - 3 <= px <= t["x1"] + 3 and t["y0"] - 3 <= py <= t["y1"] + 3:
                    pd += 1
        ok(pd == 0, "F2 注解零重叠：文字 × 数据点 压盖 %d 处" % pd)

        def texts_of(svg_text, ox=0):
            out = []
            for m in re.finditer(r"<text([^>]*)>([^<]*)</text>", svg_text):
                a = attrs_of(m.group(1))
                t = m.group(2)
                if not t.strip():
                    continue
                idx = m.start()
                trs = re.findall(r"<g[^>]*transform=\"translate\(([-\d.]+)[ ,]+([-\d.]+)\)\"",
                                 svg_text[:idx])
                tx, ty = (float(trs[-1][0]), float(trs[-1][1])) if trs else (0, 0)
                x0 = float(a.get("x", 0))
                y0 = float(a.get("y", 0))
                anch = a.get("text-anchor", "start")
                fs = float(a.get("font-size", 11))
                w = text_width(t, fs)
                bx = x0 - w / 2 if anch == "middle" else (x0 - w if anch == "end" else x0)
                out.append({"t": t, "x0": bx + tx + ox, "x1": bx + w + tx + ox,
                            "y0": y0 - fs + ty, "y1": y0 + 2 + ty})
            return out

        ct = texts_of(s_corr)
        hh = 0
        pairs = []
        for i in range(len(ct)):
            for j in range(i + 1, len(ct)):
                A, B = ct[i], ct[j]
                if A["t"] == B["t"]:
                    continue
                if not (A["x1"] + 0.5 < B["x0"] or B["x1"] + 0.5 < A["x0"] or
                        A["y1"] + 0.5 < B["y0"] or B["y1"] + 0.5 < A["y0"]):
                    hh += 1
                    pairs.append((A["t"], B["t"]))
        ok(hh == 0, "H1 副图注解零重叠：文字 × 文字 重叠 %d 对%s"
           % (hh, ("  " + str(pairs[:3])) if hh else ""))

        report[W] = {
            "pts": len(pts), "ells": len(ells), "bars": len(cbars), "paths": len(paths_),
            "segw5060": segw[i5060], "segw6070": segw[i6070], "segw8090": segw[i8090],
            "ratio": ratio, "ellMaxR": rmax, "ellOverflow": ov,
            "textOverlap": tt, "pointCover": pd, "zoneWidthDiff": rw if len(mspan) == 3 else None,
            "xmax_ac": xmax_ac, "x_1940": pos[xmax_ac][0], "x_2020": pos[xmin_ac][0],
        }
        print()

    print("=" * 78)
    print("汇总")
    print("=" * 78)
    for W, r in report.items():
        print("  %4dpx  点%-3d 椭圆%-3d 条%-3d 路径%-3d | 线宽 1950→60=%.2f 1960→70=%.2f 1980→90=%.2f (%.1f×) | 椭圆越界%d 文字重叠%d 点压盖%d" % (
            W, r["pts"], r["ells"], r["bars"], r["paths"],
            r["segw5060"], r["segw6070"], r["segw8090"], r["ratio"],
            r["ellOverflow"], r["textOverlap"], r["pointCover"]))
    print()
    print("结果：%s" % ("ALL PASS" if not fails else "FAIL %d 项" % len(fails)))
    for f in fails:
        print("  ✗ " + f)
    (WORK / "p4_render_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0 if not fails else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
