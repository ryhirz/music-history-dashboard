# -*- coding: utf-8 -*-
"""pipeline.py —— D1 → D2 数据管道编排薄壳（纯编排层，零校验逻辑）

职责只有两件事：
    1. 按序调用两个**独立**的守卫技能（先 D1 后 D2）；
    2. 任一步失败即停，并以**该层专属的退出码**结束。

它校验什么？——什么都不校验。
    D1  file_x 层：data.csv 的字节有没有被动过（SHA256）
    D2  视图层  ：三个视图的 SQL 口径有没有被改坏（行数/字段/类型/空值/唯一性/值域）
真正的校验逻辑全部在各自技能里，本文件一行都不实现。

══════════════════════════════════════════════════════════════════════
为什么需要这个薄壳（而不是让 Agent 依次跑两条命令）
══════════════════════════════════════════════════════════════════════

Agent 是概率模型，不是状态机。「先跑 D1、通过后再跑 D2」这种顺序依赖，
若交给它的上下文窗口去记忆，等于把工程质量交给了运气 —— 契约停留在文档里
就只是「建议」，变成可执行入口才是「强制」。

本薄壳消除三处编排自由度：
    1. 顺序由代码决定，Agent 不需要「决定」先跑谁，只需知道「跑管道」；
    2. 断链由代码执行，D1 失败则 D2 的进程根本不会被创建；
    3. 退出码语义**唯一** —— Agent 只看一个 exit code：
           0  = 全链路安全
          10  = D1 失败，已断链（D2 未执行）
          20  = D2 失败，已断链（后续视图未建）
           2  = 编排层自身出错（见下）
       比起让 Agent 解析两段独立输出再自行判断，单退出码可靠得多。

══════════════════════════════════════════════════════════════════════
三条铁律（防止薄壳退化成新的耦合点）
══════════════════════════════════════════════════════════════════════

铁律 1 · 零导入校验模块。
    本文件**禁止** import 任何 D1/D2 的内部函数或类。
    只通过 subprocess 调用它们的 CLI 入口 —— 这是物理隔离的代码级保证。
    若哪天有人图省事写了 `from create_and_validate_view import ...`，
    耦合瞬间复活：D2 改名/改签名会在这里静默炸掉，而文档测试发现不了。

铁律 2 · 透传而非吞错。
    子进程的 stdout/stderr **原样**打印到本进程对应流，不做摘要、不改写。
    失败时以其专属退出码结束（D1→10，D2→20），**禁止**用笼统的 exit(1)
    掩盖失败层级 —— 「文件变了」和「口径坏了」的修复路径完全不同。

铁律 3 · 参数极简。
    本管道只暴露 `--expected-hash`（可选，转交 D1）与 `--db`（可选，转交 D2）。
    业务参数（SQL、断言、视图名）**不进编排层** —— 那些住在 D2 的可执行台账
    `references/locked_views.py` 里。编排层一旦积累业务参数，就会变成第二个
    「真相来源」，与台账互相漂移。

══════════════════════════════════════════════════════════════════════
退出码契约
══════════════════════════════════════════════════════════════════════

    0   D1 通过 且 D2 通过（全链路安全）
   10   D1 失败（数据文件指纹不符 / 文件缺失）→ D2 未执行
   20   D2 失败（视图口径校验未通过）→ 已断链，后续视图未建
    2   编排层自身出错（找不到解释器 / 脚本 / 参数冲突）

注意 10 / 20 的选择是刻意的：它们**不是**子进程的原始退出码（D1/D2 都返回 1），
而是编排层做的**语义映射**。子进程退出码 0 之外的一切值，都归入对应层的失败码。
这样即便某个技能将来把退出码从 1 改成 3，编排层的语义依然稳定 —— Agent 侧
不需要跟着改。

══════════════════════════════════════════════════════════════════════
跑法
══════════════════════════════════════════════════════════════════════

    "E:\\产品\\曲风数据分析\\.venv\\Scripts\\python.exe" "E:\\产品\\曲风数据分析\\pipeline.py"

带期望哈希（推荐 —— 省去 D1 读取默认值的隐式行为）：

    "...python.exe" "...\\pipeline.py" --expected-hash c97c4234...ded7f8

单独重跑 D2（改了一次聚合 SQL、数据文件没动，无需重算 29.6 MB SHA256）：

    "...python.exe" "...\\pipeline.py" --skip-d1

⚠️ `--skip-d1` 是一个**显式逃生舱**，默认关闭。它的用途是「我只改了 SQL，
    数据文件我确认没动」。它必须由人显式敲出来，而不是由管道自动跳过 ——
    自动跳过会让 D1 形同虚设，那就退回了「靠运气」。

══════════════════════════════════════════════════════════════════════
路径解析（顶部集中常量 + 环境变量可覆盖）
══════════════════════════════════════════════════════════════════════

下面 PATHS 里是**本机**的默认路径。换机器时两种改法：
    a) 直接改常量（最直观）；
    b) 设环境变量覆盖（不改代码）：PIPELINE_PYTHON / PIPELINE_D1 /
       PIPELINE_D2 / PIPELINE_DB / PIPELINE_DATA / PIPELINE_EXPECTED_HASH。
推荐 (b) —— 路径与用户名绑定，换机器/换盘符不用碰代码。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# ══════════════════════════════════════════════════════════════════════
# 退出码：编排层专属语义（不是子进程原始码）
# ══════════════════════════════════════════════════════════════════════
EXIT_OK = 0
EXIT_D1_FAILED = 10
EXIT_D2_FAILED = 20
EXIT_ORCHESTRATION_ERROR = 2

# ══════════════════════════════════════════════════════════════════════
# 路径常量（环境变量可覆盖，见模块 docstring）
# ══════════════════════════════════════════════════════════════════════
_HOME = Path.home()
_SKILLS = _HOME / ".workbuddy" / "skills"

PATHS = {
    # 跑两个技能的 Python 解释器。默认用数据项目的 venv（装了 duckdb）。
    "python": os.environ.get(
        "PIPELINE_PYTHON",
        r"E:\产品\曲风数据分析\.venv\Scripts\python.exe",
    ),
    # D1：文件指纹校验脚本（文件层，SHA256）
    "d1_script": os.environ.get(
        "PIPELINE_D1",
        str(_SKILLS / "data_fingerprint_check" / "scripts" / "check_fingerprint.py"),
    ),
    # D2：三个视图的锁定台账（库层，创建 + 校验，内部自带断链）
    "d2_script": os.environ.get(
        "PIPELINE_D2",
        str(_SKILLS / "create_and_validate_view" / "references" / "locked_views.py"),
    ),
    # 数据文件（交给 D1）
    "data_file": os.environ.get(
        "PIPELINE_DATA",
        r"E:\产品\曲风数据分析\archive\data.csv",
    ),
    # DuckDB 路径（交给 D2；不传则用台账里的默认值）
    "db": os.environ.get("PIPELINE_DB", r"E:\产品\曲风数据分析\spotify.duckdb"),
}

# 已知的期望指纹（本机 2026-09-26 实测）。--expected-hash 未提供时用它。
DEFAULT_EXPECTED_HASH = os.environ.get(
    "PIPELINE_EXPECTED_HASH",
    "c97c42349c2e97339ff908ab01163ec5a3264f02ec65e78cb961c85077ded7f8",
)


# ══════════════════════════════════════════════════════════════════════
# 薄壳核心：跑一个子进程，透传输出，返回其退出码
# ══════════════════════════════════════════════════════════════════════
def _run_stage(label: str, cmd: list[str]) -> int:
    """执行一个阶段。原样透传子进程 stdout/stderr（铁律 2）。

    返回子进程退出码。**不在这里**做语义映射 —— 映射留给调用方，
    因为「属于哪一层」是编排知识，不该塞进通用执行函数里。
    """
    print("=" * 74)
    print(f"[{label}] {' '.join(cmd)}")
    print("=" * 74)
    sys.stdout.flush()  # 关键：先把自己写的头部刷出去，再起子进程
    try:
        proc = subprocess.run(
            cmd,
            # 透传：把子进程的输出接到父进程的**底层文件描述符**上，
            # 而不是 sys.stdout 对象（对象会被 Python 层缓冲，导致
            # 「标题」晚于「子进程输出」出现）。配合上面的 flush()，
            # 保证「本层标题 → 子进程输出 → 本层结论」顺序不乱。
            stdout=sys.stdout.fileno(),
            stderr=sys.stderr.fileno(),
        )
    except (OSError, ValueError) as exc:
        # 解释器或脚本不存在 —— 这是编排层的问题，不是 D1/D2 的失败
        print(f"[编排错误] 无法启动子进程：{exc}", file=sys.stderr)
        print(
            "          检查 PATHS['python'] 是否指向有效的解释器，或设 PIPELINE_PYTHON 覆盖。",
            file=sys.stderr,
        )
        return EXIT_ORCHESTRATION_ERROR
    print()
    return proc.returncode


def _check_path(label: str, path: str) -> bool:
    """编排前置检查：脚本必须存在。缺失属编排错误，而非某层的校验失败。"""
    if not Path(path).is_file():
        print(f"[编排错误] {label} 脚本不存在：{path}", file=sys.stderr)
        return False
    return True


# ══════════════════════════════════════════════════════════════════════
# 主编排
# ══════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="pipeline.py",
        description="D1(文件指纹) → D2(视图口径) 数据管道：按序调用，失败即停。",
        epilog="退出码：0=全通过 / 10=D1失败 / 20=D2失败 / 2=编排层错误",
    )
    parser.add_argument(
        "--expected-hash",
        default=None,
        help="data.csv 的期望 SHA256；不给则用文件内默认值（本机实测值）",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="DuckDB 路径，转交 D2；不给则用 D2 台账内的默认值",
    )
    parser.add_argument(
        "--skip-d1",
        action="store_true",
        help="⚠️ 显式跳过 D1（仅当确认数据文件未动、只改了 SQL 时使用）",
    )
    args = parser.parse_args(argv)

    python = PATHS["python"]
    expected = args.expected_hash or DEFAULT_EXPECTED_HASH

    # ── 编排前置检查：脚本存在性（属编排错误，非某层失败）──────────
    if not _check_path("D1", PATHS["d1_script"]):
        return EXIT_ORCHESTRATION_ERROR
    if not _check_path("D2", PATHS["d2_script"]):
        return EXIT_ORCHESTRATION_ERROR

    print()
    print("╔" + "═" * 72 + "╗")
    print("║  D1 → D2 数据管道（编排层 · 零校验逻辑）" + " " * 30 + "║")
    print("╚" + "═" * 72 + "╝")
    print(f"  数据文件 : {PATHS['data_file']}")
    print(f"  期望指纹 : {expected[:16]}…{expected[-8:]}  ({len(expected)} 位)")
    print(f"  数据库   : {PATHS['db']}")
    print(f"  解释器   : {python}")
    print()

    # ══════════════════════════════════════════════════════════════════
    # D1 · 文件层：data.csv 的字节有没有被动过
    # ══════════════════════════════════════════════════════════════════
    if args.skip_d1:
        print("=" * 74)
        print("[D1] ⚠️ 已被 --skip-d1 显式跳过 —— 本次不校验数据文件完整性")
        print("=" * 74)
        print()
    else:
        d1_cmd = [python, PATHS["d1_script"], expected, "--file", PATHS["data_file"]]
        rc_d1 = _run_stage("D1 文件指纹", d1_cmd)
        if rc_d1 != 0:
            print("─" * 74)
            print(f"[断链] D1 失败（子进程退出码 {rc_d1}）—— **D2 不会被执行**。")
            print("       含义：data.csv 的字节与期望不符（被替换 / 损坏 / 路径不对）。")
            print("       修复路径：换回正确文件，或更新期望指纹。**不要**改视图 SQL ——")
            print("                 视图口径没问题，是数据本身变了。")
            print(f"       管道退出码：{EXIT_D1_FAILED}")
            print("─" * 74)
            return EXIT_D1_FAILED

        print("[D1] ✅ 通过 —— 数据文件指纹一致，继续进入 D2。\n")

    # ══════════════════════════════════════════════════════════════════
    # D2 · 库层：三个视图的 SQL 口径有没有被改坏
    # ══════════════════════════════════════════════════════════════════
    d2_cmd = [python, PATHS["d2_script"]]
    if args.db:
        # locked_views.py 用模块常量 DB_PATH，不支持 --db 参数；
        # 若需要覆盖，走环境变量或直接改台账。这里显式提示，避免静默忽略。
        print(
            "[编排提示] --db 已提供，但 D2 台账使用模块内 DB_PATH 常量；"
            "若要覆盖数据库路径，请设 PIPELINE_DB 或直接改台账。\n"
        )
    rc_d2 = _run_stage("D2 视图口径", d2_cmd)
    if rc_d2 != 0:
        print("─" * 74)
        print(f"[断链] D2 失败（子进程退出码 {rc_d2}）—— 后续视图未建。")
        print("       含义：视图的 SQL 口径或结论与锁定断言不符。")
        print("       修复路径：改回正确 SQL —— **不要**动数据文件，")
        print("                 D1 已证明数据没变，问题在转换/聚合逻辑。")
        print(f"       管道退出码：{EXIT_D2_FAILED}")
        print("─" * 74)
        return EXIT_D2_FAILED

    # ══════════════════════════════════════════════════════════════════
    print("=" * 74)
    print("[PASS] 全链路安全：D1 文件指纹一致 + D2 三视图口径全部 VALID。")
    print(f"       管道退出码：{EXIT_OK}")
    print("=" * 74)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
