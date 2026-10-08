# -*- coding: utf-8 -*-
"""release/ · 生成 p4_export.json（Phase 4 渲染/交互层校验的台账真值）。

render_check4.py 与 probe4.py 需要 `EQ_ROWS`（每十年 ac/en/n）与 `EQ_SEG`
（段距离/份额/速度）。这些值在交付物里**同时存在于 d3_dashboard.html 的数据块中**，
因此本脚本直接从 HTML 解析，做到：

  · 不依赖数据库（前端数据块即真理来源）；
  · 完全确定性（同一 HTML → 同一 JSON），可复现、可 diff；
  · 落在 release/ 内，不引用任何外部文件。

输出：release/verify/p4_export.json
    { "rows": [ {dec,ac,en,n}, ... ],   # 11 行
      "seg" : [ {from,to,d,share,speed}, ... ] }  # 10 段
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

import paths

HERE = paths.HERE
HTML = paths.HTML


def _parse_blocks(text: str) -> list[dict]:
    """抽取 `{...}` 块并解析为 dict（与 check4.py 同口径）。"""
    out = []
    for blk in re.findall(r"\{([^{}]*)\}", text):
        d: dict = {}
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
        if "dec" in d or "from" in d:
            out.append(d)
    return out


def main() -> int:
    if not HTML.exists():
        print("FATAL: 看板缺失 -> %s" % HTML)
        return 1
    src = HTML.read_text(encoding="utf-8")

    m = re.search(r"const EQ_ROWS = \[(.*?)\n\];", src, re.S)
    if not m:
        print("FATAL: HTML 中找不到 EQ_ROWS 数据块")
        return 1
    rows = _parse_blocks(m.group(1))
    rows_out = [{k: d[k] for k in ("dec", "ac", "en", "n") if k in d} for d in rows]

    m2 = re.search(r"const EQ_SEG = \[(.*?)\n\];", src, re.S)
    if not m2:
        print("FATAL: HTML 中找不到 EQ_SEG 数据块")
        return 1
    seg = _parse_blocks(m2.group(1))
    seg_out = [{k: d[k] for k in ("from", "to", "d", "share", "speed") if k in d}
               for d in seg]

    if len(rows_out) != 11:
        print("WARN: EQ_ROWS 解析结果 %d 行（预期 11）" % len(rows_out))
    if len(seg_out) != 10:
        print("WARN: EQ_SEG 解析结果 %d 段（预期 10）" % len(seg_out))

    out = HERE / "p4_export.json"
    out.write_text(
        json.dumps({"rows": rows_out, "seg": seg_out}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("  [OK] 写入 %s  rows=%d  seg=%d" % (out, len(rows_out), len(seg_out)))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
