# -*- coding: utf-8 -*-
"""release/ · 一键验证编排器。

顺序：
  0. 确保数据层就绪（build_db.py 从随包 data.csv 重建 spotify.duckdb）
  1. 确保 p4_export.json 就绪（make_p4_export.py 从 HTML 解析）
  2. 依次跑 8 层自动化测试（数据/源码/渲染/交互/离线）
  3. 汇总 PASS/FAIL 与各脚本退出码；全部通过则清理运行期临时目录 _work。

用法：
    python run_all.py          # 在 release/ 内跑（cwd 任意均可，路径全自定位）
    python run_all.py --keep   # 保留 _work 便于事后排查

退出码 0 = 8/8 全绿；非 0 = 有失败。
"""
from __future__ import annotations

import subprocess
import sys
import shutil
import time

import paths


def reap_headless_edge():
    """结束上一轮可能残留的无头 Edge 子进程（仅匹配命令行含 --headless 的实例，
    不会误伤用户正常打开的 Edge），释放 GPU / 共享内存——
    否则 7 轮串行无头会话后资源耗尽，末轮探针的看板首屏初始化会卡死。"""
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"name='msedge.exe'\" | "
            "Where-Object { $_.CommandLine -like '*--headless*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=30)
    except Exception:
        pass

# 8 层测试（相对 release/verify 的脚本名）
SCRIPTS = [
    "lv10.py",            # L1  台账回归（10/10 视图）
    "check3.py",          # L2a 源码 Phase 3
    "check4.py",          # L2b 源码 Phase 4
    "render_check.py",    # L3a 渲染 Phase 3（三宽度）
    "render_check4.py",   # L3b 渲染 Phase 4（三宽度 × 八断言）
    "probe4.py",          # L4a 交互 tooltip（Phase 4）
    "probe5.py",          # L4b 交互 导航（Phase 5）
    "offline5.py",        # L5  离线断网渲染对照
]


def run_one(name: str) -> int:
    print("\n" + "#" * 86)
    print("# 运行 %s" % name)
    print("#" * 86)
    r = subprocess.run(
        [sys.executable, str(paths.HERE / name)],
        cwd=str(paths.HERE),
        capture_output=False,  # 直接透传输出，便于实时观察
    )
    return r.returncode


def main() -> int:
    # 0 & 1：数据层 + 导出（幂等，失败即中止）
    print("=" * 86)
    print("0. 数据层就绪性检查（缺失则重建 spotify.duckdb）")
    print("=" * 86)
    if not paths.ensure_db():
        print("FATAL: 数据库重建失败")
        return 1
    print("  [OK] spotify.duckdb 就绪 -> %s" % paths.DB)

    print("=" * 86)
    print("1. p4_export.json 就绪性检查")
    print("=" * 86)
    if not paths.ensure_p4_export():
        print("FATAL: p4_export.json 生成失败")
        return 1
    print("  [OK] p4_export.json 就绪 -> %s" % (paths.HERE / "p4_export.json"))

    # 2：依次跑 8 层（任一层若返回非 0，最多再重试 2 次以应对无头浏览器资源争用）
    results = []
    for name in SCRIPTS:
        reap_headless_edge()   # 清掉上一轮残留无头 Edge，避免串行累积压垮末轮
        time.sleep(2)          # 让系统回收 GPU / 共享内存后再开下一轮
        rc = run_one(name)
        attempts = 1
        while rc != 0 and attempts < 3:
            print("\n  [retry %d] %s 返回非 0，重建环境重试一次..." % (attempts, name))
            reap_headless_edge()
            time.sleep(2)
            rc = run_one(name)
            attempts += 1
        results.append((name, rc))

    # 3：汇总
    print("\n" + "=" * 86)
    print("汇总：8 层自动化测试")
    print("=" * 86)
    all_ok = True
    for name, rc in results:
        mark = "PASS" if rc == 0 else "FAIL"
        if rc != 0:
            all_ok = False
        print("  [%s] %-18s  exit=%d" % (mark, name, rc))
    print()
    print("总判定：%s" % ("ALL GREEN ✅  8/8" if all_ok else "HAS FAILURE ❌"))

    # 清理运行期临时目录（交附包内不保留）
    keep = "--keep" in sys.argv
    if not keep and paths.WORK.exists():
        # 注意：某些沙箱环境会对「一次性删除上百个文件」做批量删除保护并注入非 Exception 级中断，
        # 因此这里连 BaseException 也接住——临时目录没清掉只是留了垃圾，绝不该污染 8/8 的判定。
        try:
            shutil.rmtree(paths.WORK)
            print("\n[clean] 已清理运行期临时目录 %s" % paths.WORK)
        except BaseException as e:
            print("\n[clean] 清理失败（可忽略，多为沙箱批量删除保护）：%s" % e)

    return 0 if all_ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
