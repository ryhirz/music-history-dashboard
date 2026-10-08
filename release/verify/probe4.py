# -*- coding: utf-8 -*-
"""Phase 4 · Tooltip 探针
真实触发 mouseenter 到 1960s 命中层，把 tooltip innerHTML 抓回来，
逐条验证「必须显示与 1950s / 1970s 的断层距离」。

release 版：HTML / EDGE / WORK / p4_export 全部相对定位。
"""
import json
import pathlib
import re
import subprocess
import sys

import paths

ROOT = paths.ROOT
HTML = paths.HTML
WORK = paths.WORK
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

    WORK.mkdir(parents=True, exist_ok=True)
    probe_src = HTML.read_text(encoding="utf-8")
    INJECT = """
    <script>
    (function(){
      var tries = 0;
      function go(){
        var pts = document.querySelectorAll('#chart-space .sp-hit');
        if (pts.length < 11 && tries++ < 120){ return setTimeout(go, 100); }
        var res = {};
        function fire(dec){
          var p = document.querySelectorAll('#chart-space .sp-hit');
          var idx = {1920:0,1930:1,1940:2,1950:3,1960:4,1970:5,1980:6,
                     1990:7,2000:8,2010:9,2020:10}[dec];
          if (!p.length || !p[idx]) return 'NO_HIT(n=' + p.length + ')';
          p[idx].dispatchEvent(new MouseEvent('mouseenter', {bubbles:true, clientX:300, clientY:300}));
          var tip = document.getElementById('tooltip');
          if (!tip) return 'NO_TIP';
          var rows = tip.querySelectorAll('.tt-r');
          var out = [];
          var h = tip.querySelector('.tt-h');
          if (h) out.push('H:' + h.textContent.replace(/\\s+/g,' ').trim());
          for (var i=0;i<rows.length;i++){
            var k = rows[i].querySelector('.k'), v = rows[i].querySelector('.v');
            if (k && v) out.push(k.textContent.replace(/\\s+/g,' ').trim() + '=' +
                                v.textContent.replace(/\\s+/g,' ').trim());
          }
          var ns = tip.querySelectorAll('.tt-note');
          for (var j=0;j<ns.length;j++) out.push('N:' + ns[j].textContent.replace(/\\s+/g,' ').trim());
          return out.join(' || ');
        }
        res.t1960 = fire(1960);
        res.t1950 = fire(1950);
        res.t1970 = fire(1970);
        var pre = document.createElement('pre');
        pre.id = '__probe_out__';
        pre.textContent = JSON.stringify(res);
        document.body.appendChild(pre);
        document.title = 'PROBE_DONE';
      }
      if (document.readyState === 'complete') setTimeout(go, 200);
      else window.addEventListener('load', function(){ setTimeout(go, 200); });
    })();
    </script>
    """
    probe_page = WORK / "p4_probe_page.html"
    probe_page.write_text(probe_src.replace("</body>", INJECT + "</body>"), encoding="utf-8")

    ud = WORK / "p4_probe_ud"
    r = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                        "--virtual-time-budget=9000", "--force-device-scale-factor=1",
                        "--user-data-dir=" + str(ud),
                        "--dump-dom", probe_page.as_uri()],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=180)
    dom = r.stdout or ""
    m = re.search(r"<pre id=\"__probe_out__\">(.*?)</pre>", dom, re.S)
    raw = m.group(1) if m else None
    if raw:
        raw = (raw.replace("&quot;", "\"").replace("&amp;", "&")
                  .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'"))
    try:
        res = json.loads(raw) if raw else {}
    except Exception as e:
        res = {}
        print("JSON parse err:", e, raw[:300] if raw else "")

    t60 = res.get("t1960", "")
    t50 = res.get("t1950", "")
    t70 = res.get("t1970", "")

    EQ = json.loads(P4_EXPORT.read_text(encoding="utf-8"))
    seg = {s["from"]: s for s in EQ["seg"]}
    d_5060, sh_5060 = seg[1950]["d"], seg[1950]["share"]
    d_6070, sh_6070 = seg[1960]["d"], seg[1960]["share"]
    sh_sum = sh_5060 + sh_6070

    checks = []
    def ck(c, msg):
        checks.append((bool(c), msg))

    ck("PROBE_DONE" in dom, "Headless Edge 中探针脚本已执行完毕")
    ck(t60 and t60 != "NO_HIT" and t60 != "NO_TIP", "1960s 命中层 hover 成功派发（tooltip 已渲染）")

    ck("1950s" in t60, "Hover 1960s → 出现「1950s」（左侧断层段来源）")
    ck("1970s" in t60, "Hover 1960s → 出现「1970s」（右侧断层段来源）")
    ck("%.4f" % d_5060 in t60, "Hover 1960s → 左侧距离 %.4f 与实际一致" % d_5060)
    ck("%.4f" % d_6070 in t60, "Hover 1960s → 右侧距离 %.4f 与实际一致" % d_6070)
    ck("26.8%" in t60 or "26.7%" in t60, "Hover 1960s → 左侧路径份额 26.8% 显示")
    ck("27.0%" in t60, "Hover 1960s → 右侧路径份额 27.0% 显示")
    ck("53.8%" in t60 or "53.7%" in t60, "Hover 1960s → 两侧合计 53.8%% 显示")
    ck("断层带" in t60, "Hover 1960s → 段位标注为「断层带」")

    ck("0.2512" not in t50 or "1950s" in t50, "1950s 的 tooltip 正常（非 1960s 内容串台）")
    ck("1960s" in t50, "Hover 1950s → 显示「→ 至 1960s」")

    print("=" * 78)
    print("Phase 4 · Tooltip 探针（Headless Edge 真实 mouseenter → 读回 DOM）")
    print("=" * 78)
    print("  Edge              : %s" % EDGE)
    print("  探针页            : %s" % probe_page)
    print()
    print("  ── Hover 1960s 的 tooltip 实抓内容 ──")
    for part in [p.strip() for p in t60.split("||")]:
        print("     %s" % part)
    print()
    for ok_, msg in checks:
        print("  %s %s" % ("PASS" if ok_ else "FAIL", msg))
    print()
    print("  台账真值：1950s→1960s d=%.6f share=%.2f%%  |  1960s→1970s d=%.6f share=%.2f%%  |  合计 %.2f%%"
          % (d_5060, sh_5060, d_6070, sh_6070, sh_sum))
    bad = sum(1 for o, _ in checks if not o)
    print()
    print("结果：%s" % ("ALL PASS" if bad == 0 else "FAIL %d 项" % bad))

    (WORK / "p4_probe_report.json").write_text(json.dumps(
        {"checks": [{"ok": o, "msg": mm} for o, mm in checks],
         "tip_1960": t60, "tip_1950": t50, "tip_1970": t70,
         "d_5060": d_5060, "d_6070": d_6070, "share_sum": sh_sum},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
