# -*- coding: utf-8 -*-
"""Phase 5 · D. 离线产物「断网渲染」验证。

思路：用 Edge 的 --host-resolver-rules 把所有域名（含 CDN）解析到一个黑洞地址，
     再加 --proxy-server 指向一个不存在的本地端口，双重保证任何外部请求都拿不到数据。
     在这种环境下 dump 两个文件的 DOM：

       A. d3_dashboard.html（CDN 依赖版）→ 预期图表区退化为 .fallback 错误提示
       B. d3_dashboard.offline.html（内联版）→ 预期 SVG 完整渲染、零 fallback

     两者对照即构成「离线可用」的机器证明。

release 版：HTML / EDGE / WORK 全部相对定位。
"""
import pathlib
import re
import subprocess
import sys

import paths

ROOT = paths.ROOT
WORK = paths.WORK
EDGE = paths.find_edge()
if not EDGE:
    sys.exit("FATAL: 找不到 msedge.exe —— 请用环境变量 WB_EDGE 指定")

OFFLINE_ARGS = [
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
    "--proxy-server=http://127.0.0.1:9",
    "--disable-background-networking",
    "--disable-component-update",
    "--no-first-run",
]

fails = []


def ok(cond, msg):
    print(("    PASS  " if cond else "    FAIL  ") + msg)
    if not cond:
        fails.append(msg)


def dump(tag, path, w=1440, budget=12000):
    prof = WORK / ("p5_edge_%s" % tag)
    prof.mkdir(parents=True, exist_ok=True)
    out = WORK / ("p5_dom_%s.html" % tag)
    cmd = [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--force-device-scale-factor=1",
           "--user-data-dir=" + str(prof),
           "--virtual-time-budget=%d" % budget,
           "--window-size=%d,1400" % w,
           "--dump-dom", path.as_uri()] + OFFLINE_ARGS
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=240)
    out.write_text(r.stdout or "", encoding="utf-8")
    return out.read_text(encoding="utf-8")


def svg_count(dom, cid):
    i = dom.find('id="%s"' % cid)
    if i < 0:
        return 0
    j = dom.find("<svg", i)
    if j < 0:
        return 0
    k = dom.find("</svg>", j)
    seg = dom[j:k]
    return 1 if ("viewBox" in dom[j:j + 400] and len(seg) > 800) else 0


def count_rendered_fallback(dom):
    """只数【真的渲染出来的】fallback 元素（剥掉 <script> 块再数，避开 JS 源码里的字符串）。"""
    body = re.sub(r"<script\b.*?</script>", "", dom, flags=re.S)
    return len(re.findall(r'class="fallback"', body))


CHECKS = ["chart-macro", "chart-meso", "chart-micro", "chart-space", "chart-space-corr"]

print("=" * 78)
print("断网渲染对照（Edge host-resolver 黑洞 + 代理黑洞）")
print("=" * 78)

if not paths.HTML.exists() or not paths.HTML_OFFLINE.exists():
    print("FATAL: 看板文件缺失")
    sys.exit(1)

print()
print("A. CDN 依赖版 d3_dashboard.html —— 预期：失败（证明断网环境确实生效）")
dom_a = dump("cdn", paths.HTML)
fb_a = count_rendered_fallback(dom_a)
svg_a = sum(svg_count(dom_a, c) for c in CHECKS)
ok(fb_a > 0, "图表区渲染出 fallback 错误提示（%d 处）——断网环境已生效" % fb_a)
ok(svg_a == 0, "CDN 版无任何完整 SVG（%d 个）——未侥幸命中缓存" % svg_a)

print()
print("B. 内联离线版 d3_dashboard.offline.html —— 预期：全部渲染成功")
dom_b = dump("off", paths.HTML_OFFLINE)
fb_b = count_rendered_fallback(dom_b)
svg_b = sum(svg_count(dom_b, c) for c in CHECKS)
ok(fb_b == 0, "渲染出的 fallback 元素 = 0（实为 %d）" % fb_b)
ok(svg_b == len(CHECKS), "五个图表容器全部渲染出 SVG（%d/%d）" % (svg_b, len(CHECKS)))

for label, needle in [
    ("进度条", 'id="progress"'),
    ("侧栏目录", 'id="toc"'),
    ("角落目录", 'id="toc-mini"'),
    ("声明区块", 'id="sec-forensic"'),
    ("穿针引线①（→中观）", "thread thread-meso"),
    ("穿针引线②（→宏观）", "thread thread-macro"),
    ("四层验证表", 'class="notes fverify"'),
]:
    ok(needle in dom_b, "离线版含 %s" % label)

anchors = set(re.findall(r'data-toc="([^"]+)"', dom_b))
miss = [a for a in anchors if ('id="%s"' % a) not in dom_b]
ok(anchors and not miss, "目录锚点全部落地（%d 个，缺失 %s）" % (len(anchors), miss or "无"))

print()
print("=" * 78)
print("结果：%s" % ("ALL PASS" if not fails else "FAIL %d 项" % len(fails)))
for f in fails:
    print("  ✗ " + f)
print("=" * 78)
sys.exit(0 if not fails else 1)
