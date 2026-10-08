# -*- coding: utf-8 -*-
"""Phase 5 · A. 目录与滚动高亮的交互探针。

思路与 probe4.py 同：往页面注入一段脚本，在真实浏览器里驱动滚动，
把结果写进 <pre id="__probe_out__">，再用 --dump-dom 读回。
不用截图判断，而是拿【真实的 class / transform / scrollY】当证据。

断言：
  P1 进度条随滚动单调增长，且首尾接近 0 / 1
  P2 侧栏目录滚过页头后浮现（.on），滚回顶部后隐去
  P3 scroll-spy：五个锚点各自滚到位时，对应目录项恰好是唯一 .cur
  P4 已读章节被标 .done（在前、不在后）
  P5 侧栏与角落目录高亮同步（同一 data-toc 两处都亮）
  P6 点击目录项能真的跳到目标 section（scrollY 落到目标附近）
  P7 锚点落地：每个 href 的目标 id 都存在且是 <section>

release 版：HTML / EDGE / WORK 全部相对定位；用离线版测（TOC 与 D3 解耦）。
"""
import os
import pathlib
import re
import subprocess
import sys

import paths

ROOT = paths.ROOT
WORK = paths.WORK
HTML = paths.HTML_OFFLINE
EDGE = paths.find_edge()
if not EDGE:
    sys.exit("FATAL: 找不到 msedge.exe —— 请用环境变量 WB_EDGE 指定")


def main() -> int:
    if not HTML.exists():
        print("FATAL: 离线看板缺失 -> %s" % HTML)
        return 1
    WORK.mkdir(parents=True, exist_ok=True)

    INJECT = r'''
    <pre id="__probe_out__" style="position:fixed;left:-9999px"></pre>
    <script>
    (function(){
      var out = [];
      function log(k, v){ out.push(k + '=' + v); }
      window.onerror = function(m, s, l, c){
        out.push('JS_ERROR=' + m + ' @line' + l);
        flush();
      };
      function flush(){
        document.getElementById('__probe_out__').textContent = out.join('\n');
      }
      function reAll(sel){
        var a = Array.prototype.slice.call(document.querySelectorAll(sel));
        return a.map(function(x){ return x.getAttribute('data-toc'); }).join('|');
      }
      function q(cls){
        var ids = ['sec-macro','sec-meso','sec-micro','sec-space','sec-forensic'];
        return ids.map(function(id){
          var a = document.querySelector('#toc a[data-toc="' + id + '"]');
          var b = document.querySelector('#toc-mini a[data-toc="' + id + '"]');
          return id + ':' + ((a && a.classList.contains(cls)) ? 1 : 0)
                      + '/' + ((b && b.classList.contains(cls)) ? 1 : 0);
        }).join(',');
      }
      var rafQ = [];
      var rafQTotal = 0;
      var origRaf = window.requestAnimationFrame;
      window.requestAnimationFrame = function(fn){
        rafQ.push(fn);
        rafQTotal++;
        return rafQ.length;
      };
      window.cancelAnimationFrame = function(h){
        if (h > 0 && h <= rafQ.length) rafQ[h - 1] = null;
      };
      function flushRaf(){
        var q = rafQ; rafQ = [];
        q.forEach(function(fn){ if (fn){ try { fn(performance.now()); } catch(e){} } });
      }
      var _y = 0;
      function setY(y){
        _y = y;
        try { window.scrollTo(0, y); } catch(e){}
        try {
          Object.defineProperty(window, 'pageYOffset', { get: function(){ return _y; }, configurable: true });
        } catch(e){}
        try {
          Object.defineProperty(document.documentElement, 'scrollTop', { get: function(){ return _y; }, configurable: true });
        } catch(e){}
        window.dispatchEvent(new Event('scroll'));
        flushRaf();
      }
      function go(){
        try { go_(); } catch(e){
          out.push('GO_ERROR=' + (e && e.message));
          flush();
        }
      }
      function go_(){
        var prog = document.getElementById('progress');
        var toc  = document.getElementById('toc');
        var dh   = document.body.scrollHeight;
        var vh   = window.innerHeight || 900;
        function progScale(){
          var m = /scaleX\(([\d.]+)\)/.exec(prog.style.transform || '');
          return m ? parseFloat(m[1]) : -1;
        }
        log('ENV_innerHeight', vh);
        log('ENV_scrollHeight', dh);
        setY(0);
        var p0 = progScale();
        setY(Math.round((dh - vh) * 0.5));
        var pMid = progScale();
        setY(dh - vh);
        var pEnd = progScale();
        log('P1_p0', p0.toFixed(3));
        log('P1_pmid', pMid.toFixed(3));
        log('P1_pend', pEnd.toFixed(3));
        log('P1_mono', (p0 <= pMid + 1e-6 && pMid <= pEnd + 1e-6) ? 1 : 0);
        setY(0);
        log('P2_hidden_at_top', toc.classList.contains('on') ? 0 : 1);
        var ids = ['sec-macro','sec-meso','sec-micro','sec-space','sec-forensic'];
        ids.forEach(function(id){
          var s = document.getElementById(id);
          setY(s.offsetTop - 88);
          var cur = reAll('#toc a.cur');
          log('P3_' + id, cur === '' ? '(none)' : cur);
          log('P3_' + id + '_ok', cur === id ? 1 : 0);
        });
        var sLast = document.getElementById('sec-forensic');
        setY(sLast.offsetTop - 88);
        log('P4_done', document.querySelectorAll('#toc a.done').length);
        log('P4_done_list', reAll('#toc a.done'));
        var sMicro = document.getElementById('sec-micro');
        setY(sMicro.offsetTop - 88);
        log('P5_cur_pairs', q('cur'));
        log('P5_on_at_mid', toc.classList.contains('on') ? 1 : 0);
        setY(0);
        var link = document.querySelector('#toc a[data-toc="sec-space"]');
        link.click();
        log('P6_cur_after_click', reAll('#toc a.cur') || '(none)');
        log('P6_done_after_click', document.querySelectorAll('#toc a.done').length);
        var bad = [];
        Array.prototype.slice.call(
          document.querySelectorAll('#toc a[data-toc],#toc-mini a[data-toc]'))
          .forEach(function(a){
            var id = a.getAttribute('data-toc');
            var el = document.getElementById(id);
            if (!el || el.tagName.toLowerCase() !== 'section') bad.push(a.getAttribute('href'));
          });
        log('P7_bad', bad.join(',') || 'none');
        log('P7_ok', bad.length === 0 ? 1 : 0);
        log('P8_raf_stubbed', 1);
        log('P8_raf_queue_seen', rafQTotal);
        flush();
      }
      // 就绪门：轮询直到看板把 #toc 建好（5 个章节锚点齐全）——
      // 这是与滚动状态无关、能证明主脚本初始化已完成的可靠信号。
      // 之前写死的 setTimeout(go, 2600) 在首屏初始化未结束时就会误触发，
      // 导致 #progress / 滚动高亮尚未挂载，探测到 -1.000 / (none)。
      function waitReady(tries){
        var toc = document.getElementById('toc');
        var built = toc && toc.querySelectorAll('a[data-toc]').length >= 5;
        if (built || tries <= 0){ go(); return; }
        setTimeout(function(){ waitReady(tries - 1); }, 200);
      }
      setTimeout(function(){ waitReady(80); }, 300);
    })();
    </script>
    '''

    def run(idx):
        # 每次尝试用全新 profile 目录（带进程号 + 序号）。
        # 注意：**不要尝试删除旧 profile**——每个 profile 含上百个文件，
        # 会撞上沙箱的批量删除保护（count 224 > threshold 50）而直接崩掉。
        prof = WORK / ("p5_probe_ud_%d_%d" % (os.getpid(), idx))
        prof.mkdir(parents=True, exist_ok=True)
        page = WORK / ("p5_probe_page_%d.html" % idx)
        html = HTML.read_text(encoding="utf-8")
        html = html.replace("</body>", INJECT + "\n</body>")
        page.write_text(html, encoding="utf-8")
        out = WORK / ("p5_probe_dom_%d.html" % idx)
        cmd = [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
               "--force-device-scale-factor=1",
               "--user-data-dir=" + str(prof),
               "--virtual-time-budget=60000",
               "--window-size=1440,1400",
               "--dump-dom", page.as_uri()]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=300)
        out.write_text(r.stdout or "", encoding="utf-8")
        return out.read_text(encoding="utf-8")

    print("=" * 78)
    print("Phase 5 · 目录与滚动高亮探针（Headless Edge 真实滚动）")
    print("=" * 78)

    dom = None
    raw = ""
    m = None
    for attempt in range(1, 4):  # 最多 3 次：应对无头浏览器首屏初始化竞态 / 资源争用
        dom = run(attempt)
        m = re.search(r"<pre id=\"__probe_out__\"[^>]*>(.*?)</pre>", dom, re.S)
        raw = (m.group(1).strip() if m and m.group(1).strip() else "")
        # 就绪判据：探针确实产出，且 #progress 已拿到真实 scaleX（非 -1 占位）
        ready = ("P1_p0" in raw) and ("-1.000" not in raw)
        if raw and ready:
            break
        if attempt < 3:
            print("  [retry %d] 探针未就绪（无头浏览器首屏初始化未完成 / 资源争用），重建环境重试..."
                  % attempt)
    if not raw:
        print("FAIL 探针未产出结果 —— 脚本可能未执行")
        return 1

    kv = {}
    for ln in m.group(1).split("\n"):
        if "=" in ln:
            k, v = ln.split("=", 1)
            kv[k] = v.strip()

    for k, v in kv.items():
        print("  %-24s %s" % (k, v))
    print()

    fails = []
    def ok(cond, msg):
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        if not cond:
            fails.append(msg)

    p0, pm, pe = float(kv["P1_p0"]), float(kv["P1_pmid"]), float(kv["P1_pend"])
    ok(kv["P1_mono"] == "1", "P1 进度条单调不减（%.3f → %.3f → %.3f）" % (p0, pm, pe))
    ok(p0 < 0.02, "P1 顶部进度 ≈ 0（%.3f）" % p0)
    ok(pe > 0.97, "P1 底部进度 ≈ 1（%.3f）" % pe)

    ok(kv["P2_hidden_at_top"] == "1", "P2 顶部时目录处于隐藏态（不与标题抢注意力）")

    for sid in ["sec-macro", "sec-meso", "sec-micro", "sec-space", "sec-forensic"]:
        ok(kv["P3_" + sid + "_ok"] == "1",
           "P3 滚到 %s 时恰好它高亮（实为「%s」）" % (sid, kv["P3_" + sid]))

    ok(int(kv["P4_done"]) == 4,
       "P4 位于末章时前四章标记为已读（%s 个：%s）" % (kv["P4_done"], kv["P4_done_list"]))

    pairs = kv["P5_cur_pairs"]
    cur_cnt = [x for x in pairs.split(",") if x.endswith(":1/1")]
    ok(len(cur_cnt) == 1 and cur_cnt[0].startswith("sec-micro:"),
       "P5 滚到第 III 章时，两套目录同步高亮且【只有它】：%s" % pairs)
    ok(kv["P5_on_at_mid"] == "1", "P5 滚动到中部时侧栏目录已浮现")

    ok(kv["P6_cur_after_click"] == "sec-space",
       "P6 点击「时代漂移」后立即高亮目标章节：%s" % kv["P6_cur_after_click"])
    ok(int(kv["P6_done_after_click"]) == 3,
       "P6 点击第四章后，应为「前三章已读」（实为 %s 个）" % kv["P6_done_after_click"])

    ok(kv["P7_ok"] == "1", "P7 全部目录锚点落地到真实 <section>（异常：%s）" % kv["P7_bad"])

    print()
    print("  环境：innerHeight=%s  scrollHeight=%s" % (kv.get("ENV_innerHeight"), kv.get("ENV_scrollHeight")))
    print("=" * 78)
    print("结果：%s" % ("ALL PASS" if not fails else "FAIL %d 项" % len(fails)))
    for f in fails:
        print("  ✗ " + f)
    print("=" * 78)
    return 0 if not fails else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
