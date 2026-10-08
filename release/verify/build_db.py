# -*- coding: utf-8 -*-
"""release/ · 0 层：从随包数据重建 spotify.duckdb。

为什么必须有这一步
──────────────────
交付的 `spotify.duckdb` 里 **一张物理表都没有** —— 11 个对象全是 VIEW。
其中根视图 `raw_tracks` 的定义是：

    CREATE VIEW raw_tracks AS
    SELECT * FROM read_csv_auto('E:\\产品\\曲风数据分析\\archive\\data.csv', ...)

也就是说：**这个 .duckdb 文件本身不含任何数据，它只是指向 data.csv 的一串
查询定义**。把文件复制到别的目录并不会让它"带走数据"，反而会带着**原始机器
的绝对路径** —— 在别的机器上一切查询都会报 `IOException: No files found`。

更隐蔽的风险：如果直接复用原工作区的 .duckdb，`release/verify/` 下的脚本
会**静默验证原工作区的数据**，「在干净目录下跑通」就变成了假命题。

本脚本做两件事，缺一不可：
  1. 用**本目录相对定位**的路径重建 raw_tracks 视图（把绝对路径换成
     release/ 内的 archive/data.csv），使整条链路真正自包含；
  2. 依次重建其余 10 个衍生视图 —— 全部从 `locked_views.py` 的**同一份
     锁定口径**生成，不手抄 SQL，避免台账与交付物漂移。

跑法：
    python build_db.py        （也可被 paths.ensure_db() 自动调用）

退出码 0 = 11 个对象全部建立成功；1 = 失败。
幂等：全部使用 CREATE OR REPLACE，可反复重跑。
"""
from __future__ import annotations

import pathlib
import sys

import paths

HERE = paths.HERE          # release/verify
ROOT = paths.ROOT         # release
CSV = paths.CSV           # release/data/archive/data.csv
DB = paths.DB             # release/data/spotify.duckdb


def main() -> int:
    import duckdb

    if not CSV.exists():
        print("FATAL: 随包数据缺失 -> %s" % CSV)
        return 1

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))

    # ── 步骤 1：根视图 raw_tracks，路径改写为 release 内的相对定位 ──────
    # ⚠️ DuckDB 的 read_csv_auto 路径参数不接受参数化占位符，只能拼字符串。
    #    这里用 as_posix() 规避 Windows 反斜杠被当转义符的问题；
    #    单引号转义以防路径含 ' （本机路径不含，但写成防御式）。
    csv_lit = CSV.as_posix().replace("'", "''")
    con.execute(
        "CREATE OR REPLACE VIEW raw_tracks AS "
        "SELECT * FROM read_csv_auto('%s', header=true, ignore_errors=true)" % csv_lit
    )
    n_raw = con.execute("SELECT count(*) FROM raw_tracks").fetchone()[0]
    print("  [OK] raw_tracks                 rows=%d" % n_raw)

    # ── 步骤 2：其余 10 个衍生视图，口径来自 locked_views.py ─────────────
    # 刻意 import 而不是复制 SQL：确保交付的库与台账**同源**。
    locked_dir = HERE / "skill_refs" / "references"
    if not locked_dir.exists():
        print("FATAL: 缺少锁定口径文件 -> %s" % locked_dir)
        return 1

    sys.path.insert(0, str(locked_dir))
    from locked_views import VIEWS  # noqa: E402

    bad = 0
    for name, sql, _rules in VIEWS:
        try:
            con.execute(sql)
            rows = con.execute("SELECT count(*) FROM %s" % name).fetchone()[0]
            print("  [OK] %-28s rows=%d" % (name, rows))
        except Exception as e:                      # noqa: BLE001
            bad += 1
            print("  [FAIL] %-26s %s" % (name, e))

    # ── 步骤 3：落盘并回读自检 ────────────────────────────────────────
    con.close()
    con2 = duckdb.connect(str(DB), read_only=True)
    objs = con2.execute(
        "SELECT table_name FROM information_schema.tables ORDER BY table_name"
    ).fetchall()
    con2.close()

    print()
    print("  DB 文件     : %s (%.2f MB)" % (DB, DB.stat().st_size / 1048576))
    print("  对象总数    : %d（1 根视图 + 10 衍生视图）" % len(objs))
    print("  重建结果    : %s" % ("ALL OK" if bad == 0 and len(objs) == 11 else "HAS FAILURE"))
    return 0 if (bad == 0 and len(objs) == 11) else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("=" * 78)
    print("release/ 数据层重建（相对定位 + 锁定口径）")
    print("=" * 78)
    sys.exit(main())
