# -*- coding: utf-8 -*-
"""10/10 台账回归汇总（读 locked_views.py 的 JSON 凭证并汇总）。

release 版：不写死任何绝对路径 —— skill 与输出都相对本文件定位。
"""
import json
import pathlib
import subprocess
import sys

import paths

HERE = paths.HERE
ROOT = paths.ROOT
SKILL = HERE / "skill_refs" / "references" / "locked_views.py"
OUT = HERE / "lv10_report.txt"


def main() -> int:
    if not SKILL.exists():
        print("FATAL: 缺少锁定口径 -> %s" % SKILL)
        return 1

    # 在 release 根目录下运行子进程，使其内部相对定位生效
    p = subprocess.run(
        [sys.executable, str(SKILL)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(ROOT),
    )
    OUT.write_text(
        p.stdout + "\n=== STDERR ===\n" + (p.stderr or ""), encoding="utf-8"
    )

    t = p.stdout
    # 注意：verbose 输出里有 [PASS] 前缀，不能用 index('[') 定位；锚定 JSON 凭证标题
    marker = "完整 JSON 凭证："
    i = t.index(marker) + len(marker)
    i = t.index("[", i)
    j = t.rindex("]") + 1
    data = json.loads(t[i:j])
    print("视图数 = %d" % len(data))
    bad = 0
    for e in data:
        a = e.get("assertions", {})
        ok = e.get("status") == "VALID" and all(v == "pass" for v in a.values())
        if not ok:
            bad += 1
        print("  %s %-26s %-7s rows=%-7s %s" % (
            "OK  " if ok else "FAIL",
            e.get("view", "?"), e.get("status"), e.get("rows"),
            " ".join("%s=%s" % kv for kv in a.items()),
        ))
    print()
    print("全绿 = %s  (%d/%d)" % (bad == 0, len(data) - bad, len(data)))
    print("子进程退出码 = %d" % p.returncode)
    return 0 if bad == 0 and p.returncode == 0 else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
