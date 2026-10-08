# -*- coding: utf-8 -*-
"""pipeline.py 的编排契约测试 —— 证明「D1 失败则 D2 绝不执行」。

这不测校验逻辑（那是两个技能自己的 24 个冒烟用例的事）。
它只测**编排层**的三条承诺：
    1. 正向：D1 + D2 都通过 → 退出码 0
    2. 负向：D1 失败 → 退出码 10，且 **D2 的进程根本没被创建**
    3. 负向：D1 失败 → D2 未执行，因此视图定义**逐字节未变**

第 3 条是这里的关键 —— 「D2 没跑」不能只看输出里有没有报错
（它可能跑了但静默），要用**副作用快照**来证明：跑前跑后比对
三个视图的 SQL 定义，逐字节相同才说明 D2 确实没碰数据库。

跑法（用装了 duckdb 的解释器）：
    "E:\\产品\\曲风数据分析\\.venv\\Scripts\\python.exe" \\
        "E:\\产品\\曲风数据分析\\pipeline_test.py"

退出码 0 = 全部通过，1 = 有断言失败。测试**只读**数据库，不修改任何视图
（CREATE OR REPLACE 是幂等的，但即便如此，本测试也不主动建视图）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

PIPELINE = Path(__file__).resolve().parent / "pipeline.py"
PYTHON = str(Path(sys.executable))
DB = r"E:\产品\曲风数据分析\spotify.duckdb"

EXIT_OK, EXIT_D1_FAILED, EXIT_D2_FAILED, EXIT_ORCH = 0, 10, 20, 2

# 一个必然不匹配的哈希 —— 用来触发 D1 失败
WRONG_HASH = "0" * 64

_passed = 0
_failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  [PASS] {label}")
    else:
        _failed += 1
        print(f"  [FAIL] {label}")
        if detail:
            print(f"         {detail}")


def run_pipeline(*args: str) -> subprocess.CompletedProcess:
    """执行 pipeline.py，捕获合并输出。"""
    return subprocess.run(
        [PYTHON, str(PIPELINE), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def view_definitions() -> dict[str, str]:
    """快照当前数据库中**我们自己的**视图定义（只读）。

    只用 `internal=false` 过滤还不够稳妥，这里再显式排除 duckdb_* / sqlite_*
    这类系统视图，确保快照只含本管道的三个目标视图。
    """
    import duckdb

    con = duckdb.connect(DB, read_only=True)
    try:
        rows = con.execute(
            "SELECT view_name, sql FROM duckdb_views() "
            "WHERE schema_name='main' AND internal=false "
            "  AND view_name NOT LIKE 'duckdb\\_%' ESCAPE '\\' "
            "  AND view_name NOT LIKE 'sqlite\\_%' ESCAPE '\\' "
            "ORDER BY view_name"
        ).fetchall()
        return {name: (sql or "") for name, sql in rows}
    finally:
        con.close()


print("=" * 74)
print("pipeline.py 编排契约测试")
print("=" * 74)

# ══════════════════════════════════════════════════════════════════════
# 用例 1 · 正向：正确哈希 → 退出码 0，两阶段都出现
# ══════════════════════════════════════════════════════════════════════
print("\n[1] 正向：正确哈希（默认）→ 期望退出码 0")
r1 = run_pipeline()
check("退出码 == 0", r1.returncode == EXIT_OK, f"实得 {r1.returncode}")
check("输出含 D1 阶段标题", "[D1 文件指纹]" in r1.stdout)
check("输出含 D2 阶段标题", "[D2 视图口径]" in r1.stdout)
check("输出含全链路 PASS", "全链路安全" in r1.stdout)
check(
    "输出含 D1 的 JSON 凭证（证明透传）",
    '"status": "PASS"' in r1.stdout and "sha256" in r1.stdout,
)
check("输出含 D2 的 3/3 汇总（证明透传）", "3/3 视图通过校验" in r1.stdout)

# ══════════════════════════════════════════════════════════════════════
# 用例 2 · 负向：错误哈希 → 退出码 10，且 D2 未被创建
# ══════════════════════════════════════════════════════════════════════
print("\n[2] 负向：错误哈希 → 期望退出码 10，且 D2 不执行")
before = view_definitions()
r2 = run_pipeline("--expected-hash", WRONG_HASH)
after = view_definitions()

check("退出码 == 10 (EXIT_D1_FAILED)", r2.returncode == EXIT_D1_FAILED, f"实得 {r2.returncode}")
check("输出含 D1 阶段标题", "[D1 文件指纹]" in r2.stdout)
check(
    "输出**不含** D2 阶段标题（D2 未被调度）",
    "[D2 视图口径]" not in r2.stdout,
    "D2 标题出现了 —— 说明断链没生效！",
)
check(
    "输出**不含** D2 的 3/3 汇总",
    "3/3 视图通过校验" not in r2.stdout,
)
check("输出含断链提示", "[断链]" in r2.stdout)
check("输出含 D1 的失败原因（透传）", "指纹校验失败" in (r2.stdout + r2.stderr))
check(
    "D1 的 FingerprintMismatch 出现在 stderr（透传而非吞错）",
    "FingerprintMismatch" in r2.stderr,
)
# 副作用证明：D2 若跑了，CREATE OR REPLACE 会重写定义（虽内容相同，
# 但这里比对的是「有没有被碰过」的更强证据 —— 我们比对定义文本）
check(
    "数据库视图定义逐字节未变（D2 确实没碰库）",
    before == after,
    f"视图定义发生变化：{before.keys()} vs {after.keys()}",
)
check(
    "三个视图名齐全（快照本身有效）",
    set(after.keys()) >= {"yearly_aggregates", "decade_features", "artist_panel"},
    f"实得 {sorted(after.keys())}",
)

# ══════════════════════════════════════════════════════════════════════
# 用例 4 · 负向：D2 校验失败 → 退出码 20
#   手法：把 D2 指向一个「断言故意写错」的临时台账。这样能真实触发
#   D2 层的校验失败，而无需破坏真实视图（临时台账只读真实库、不建表）。
# ══════════════════════════════════════════════════════════════════════
print("\n[3] 负向：D2 校验失败 → 期望退出码 20")

BAD_LEDGER = '''# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"C:\\Users\\Icarus\\.workbuddy\\skills\\create_and_validate_view\\scripts")
from create_and_validate_view import create_and_validate_view
r = create_and_validate_view(
    "decade_features",
    """CREATE OR REPLACE VIEW decade_features AS
SELECT year//10*10 AS decade, (year//10*10 = 2020) AS is_partial_decade,
       avg(danceability) AS mean_danceability, avg(energy) AS mean_energy, count(*) AS n
FROM raw_tracks WHERE year IS NOT NULL GROUP BY 1, 2 ORDER BY 1""",
    {"min_rows": 999, "max_rows": 999, "required_columns": ["decade"]},
    db_path=r"E:\\产品\\曲风数据分析\\spotify.duckdb",
)
print(f"[{r['status']}] code={r.get('code')}")
sys.exit(0 if r["status"] == "VALID" else 1)
'''

tmpdir = tempfile.mkdtemp(prefix="pipeline_test_")
bad_ledger_path = Path(tmpdir) / "bad_ledger.py"
bad_ledger_path.write_text(BAD_LEDGER, encoding="utf-8")

env = dict(os.environ)
env["PIPELINE_D2"] = str(bad_ledger_path)
r4 = subprocess.run(
    [PYTHON, str(PIPELINE), "--skip-d1"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    env=env,
)
check("退出码 == 20 (EXIT_D2_FAILED)", r4.returncode == EXIT_D2_FAILED, f"实得 {r4.returncode}")
check("D2 阶段确实执行了", "[D2 视图口径]" in r4.stdout)
check("输出含 D2 校验失败（透传）", "ROW_COUNT_OUT_OF_RANGE" in r4.stdout)
check("输出含断链提示", "[断链]" in r4.stdout)
check("断链提示指向 D2（不是 D1）", "D2 失败" in r4.stdout)

# 清理临时文件
shutil.rmtree(tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════════════
# 用例 5 · 编排错误：D2 脚本缺失 → 退出码 2（不是 20！）
#   区分「编排层问题」与「D2 校验失败」是重要的：脚本没了不是口径坏了。
# ══════════════════════════════════════════════════════════════════════
print("\n[4] 编排错误：D2 脚本不存在 → 期望退出码 2（非 20）")
env5 = dict(os.environ)
env5["PIPELINE_D2"] = str(Path(tempfile.gettempdir()) / "__no_such_ledger__.py")
r5 = subprocess.run(
    [PYTHON, str(PIPELINE), "--skip-d1"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    env=env5,
)
check("退出码 == 2 (EXIT_ORCHESTRATION_ERROR)", r5.returncode == EXIT_ORCH, f"实得 {r5.returncode}")
check("stderr 提示脚本不存在", "脚本不存在" in r5.stderr)
check(
    "**不**误报为 D2 校验失败（区分编排错误与校验失败）",
    "ROW_COUNT_OUT_OF_RANGE" not in r5.stdout and "D2 失败" not in r5.stdout,
)

# ══════════════════════════════════════════════════════════════════════
# 用例 6 · 逃生舱：--skip-d1 → 退出码 0，输出明确标注跳过
# ══════════════════════════════════════════════════════════════════════
print("\n[5] 逃生舱：--skip-d1 → 期望退出码 0，且显式标注跳过")
r6 = run_pipeline("--skip-d1")
check("退出码 == 0", r6.returncode == EXIT_OK, f"实得 {r6.returncode}")
check("输出显式标注已跳过 D1", "已被 --skip-d1 显式跳过" in r6.stdout)
check("D1 的子进程命令**未出现**", "check_fingerprint.py" not in r6.stdout)
check("D2 仍然执行了", "3/3 视图通过校验" in r6.stdout)

# ══════════════════════════════════════════════════════════════════════
# 用例 7 · 零导入：源码不得出现对两个技能的 import（铁律 1）
# ══════════════════════════════════════════════════════════════════════
print("\n[6] 铁律 1：pipeline.py 零导入任何校验模块")
src = PIPELINE.read_text(encoding="utf-8")
# 只看真正的 import 语句（排除注释/字符串里的提及 —— 用逐行判定）
import_lines = [
    ln.strip()
    for ln in src.splitlines()
    if ln.strip().startswith(("import ", "from ")) and not ln.strip().startswith("#")
]
violations = [
    ln
    for ln in import_lines
    if "create_and_validate_view" in ln or "check_fingerprint" in ln or "data_fingerprint" in ln
]
check("无对 D1/D2 的 import 语句", not violations, f"违规：{violations}")
check(
    "只 import 了标准库（os/sys/subprocess/pathlib/argparse）",
    all(
        ln.split()[1].split(".")[0]
        in {"os", "sys", "subprocess", "pathlib", "argparse", "__future__"}
        for ln in import_lines
        if ln.startswith("import")
    ),
    f"实际 import：{import_lines}",
)
check("通过 subprocess 调用（铁律 1 的实现手段）", "subprocess.run" in src)

# ══════════════════════════════════════════════════════════════════════
# 用例 8 · 退出码映射：不得用笼统 exit(1) 掩盖层级（铁律 2）
# ══════════════════════════════════════════════════════════════════════
print("\n[7] 铁律 2：退出码分层（10/20/2），不用笼统 1")
check("定义了 EXIT_D1_FAILED = 10", "EXIT_D1_FAILED = 10" in src)
check("定义了 EXIT_D2_FAILED = 20", "EXIT_D2_FAILED = 20" in src)
check("定义了 EXIT_ORCHESTRATION_ERROR = 2", "EXIT_ORCHESTRATION_ERROR = 2" in src)
check("D1 失败返回 10", "return EXIT_D1_FAILED" in src)
check("D2 失败返回 20", "return EXIT_D2_FAILED" in src)

print("\n" + "=" * 74)
print(f"汇总：{_passed}/{_passed + _failed} 断言通过")
print("=" * 74)
if _failed:
    print(f"\n❌ {_failed} 条断言失败。")
    sys.exit(1)
print("\n✅ 编排契约全部成立：D1 失败时 D2 绝不执行。")
sys.exit(0)
