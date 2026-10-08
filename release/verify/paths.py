# -*- coding: utf-8 -*-
"""release/verify · 统一路径与运行时自定位。

设计目标：让 verify/ 下的所有脚本在「脱离原工作区」后依然能用 ——
所有路径都相对本文件所在的 release 根目录定位，绝不写死 E:\\产品\\曲风数据分析。

层级：
    paths.py            → release/verify/paths.py
    HERE  = release/verify
    ROOT  = release
    DATA  = release/data
    DB    = release/data/spotify.duckdb        （首次运行由 build_db.py 从 CSV 重建）
    HTML  = release/d3_dashboard.html          （CDN 依赖版，源码/渲染层校验对象）
    HTMLO = release/d3_dashboard.offline.html  （完全离线版，交互/离线层校验对象）
    WORK  = release/verify/_work               （运行期临时目录，交付包内不保留）
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent          # release/verify
ROOT = HERE.parent                                      # release
DATA = ROOT / "data"
DB = DATA / "spotify.duckdb"
HTML = ROOT / "d3_dashboard.html"
HTML_OFFLINE = ROOT / "d3_dashboard.offline.html"
CSV = DATA / "archive" / "data.csv"
WORK = HERE / "_work"
PY = sys.executable

# 默认 Node（仅用于 `node --check` 校验内联 JS 语法，版本不敏感）。
# 可用环境变量 WB_NODE 覆盖，便于在他机复跑。
NODE_DEFAULT = r"C:\Users\Icarus\.workbuddy\binaries\node\versions\22.12.0\node.exe"


def node() -> str:
    return os.environ.get("WB_NODE") or NODE_DEFAULT


def find_edge() -> str | None:
    """定位 Headless Edge。可用环境变量 WB_EDGE 覆盖。"""
    candidates = [
        os.environ.get("WB_EDGE"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if c and pathlib.Path(c).exists():
            return c
    return None


def ensure_db() -> bool:
    """确保 release 内的 duckdb 就绪（指向 release/data/archive/data.csv）。

    返回 True 表示可用。若文件缺失或 raw_tracks 视图不可用，则调用 build_db.py 重建。
    这是 release 能「在干净目录下 100% 跑通」的关键：不依赖原工作区任何文件。
    """
    if DB.exists():
        try:
            import duckdb
            con = duckdb.connect(str(DB), read_only=True)
            con.execute("SELECT count(*) FROM raw_tracks").fetchone()
            con.close()
            return True
        except Exception:
            # 视图不可用（例如陈旧副本）→ 重建
            pass
    WORK.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [PY, str(HERE / "build_db.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        sys.stderr.write(r.stdout + "\n" + r.stderr)
    return DB.exists()


def ensure_p4_export() -> bool:
    """确保 p4_export.json（render_check4 / probe4 的台账真值）就绪。"""
    out = HERE / "p4_export.json"
    if out.exists():
        return True
    r = subprocess.run(
        [PY, str(HERE / "make_p4_export.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        sys.stderr.write(r.stdout + "\n" + r.stderr)
    return out.exists()


if __name__ == "__main__":
    print("HERE =", HERE)
    print("ROOT =", ROOT)
    print("DB   =", DB, "exists=", DB.exists())
    print("CSV  =", CSV, "exists=", CSV.exists())
    print("node =", node())
    print("edge =", find_edge())
