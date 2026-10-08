#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
create_and_validate_view
========================

在 DuckDB 上创建一个分析视图，并在**同一个连接**里立刻回读校验。

── 为什么创建和校验必须同一个连接 ──────────────────────────────
DuckDB 单文件是单写者模型。CREATE 和校验若分两次连接做，中间要么被别的
写连接锁住，要么读到的是别人改过的定义。同一个连接里做，读到的必定是
自己刚写的那一份 —— 这就是「事务一致性」在这里的实际含义。

── 为什么不用 SELECT * 取结果集 ────────────────────────────────
「枚出行数」和「拿到列签名」这两件事，在数据库内部用 count(*) 与 DESCRIBE
就能完成。把十几万行拉进 Python 内存，只为了数出行数，是纯浪费。
需要肉眼看口径时，用 sample_rows 取前 N 行即可。

── 为什么失败不短路 ────────────────────────────────────────────
「行数不对」和「列还缺了一个」经常同时发生。短路只会报第一件，
收集全部失败项一次报出，改一轮就能过，而不是修一个跑一次。

── 为什么拒绝未知规则键 ────────────────────────────────────────
规则键拼错（min_row 写成 min_rows）如果被静默忽略，那条断言就变成了
「没校验」，闸门形同虚设却毫无提示。所以未知键一律拒绝，宁可报错。

── 为什么 column_types 是严格字面比对 ──────────────────────────
不做等价类归一（不把 BIGINT / INTEGER 视为同类）。理由：本技能是交付闸门，
价值在于「锁死口径」。类型宽度的变化今天可能无害，但它是一个信号 ——
说明有人动过 create_sql，而闸门存在的意义正是抓住这种「有人动过」。
宁可误报让人看一眼，也别静默放过。

── 为什么 value_bounds 容忍 NULL ───────────────────────────────
NULL 表示「这个值未知」，未知不等于越界。把 NULL 算作越界会让任何含空值的
视图都过不了值域闸门，而空值该不该存在是 null_check_columns 的职责 ——
两个键各管一件事，不要互相顶替。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

try:
    import duckdb
except ImportError:
    sys.stdout.write(
        json.dumps(
            {
                "step": "create_and_validate_view",
                "status": "INVALID",
                "code": "INVALID_ARGS",
                "reason": "缺少 duckdb 依赖。请改用项目 venv 的解释器运行："
                r"E:\产品\曲风数据分析\.venv\Scripts\python.exe",
                "failures": [{"code": "INVALID_ARGS", "detail": "No module named 'duckdb'"}],
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    sys.exit(1)

STEP = "create_and_validate_view"

DEFAULT_DB_PATH = r"E:\产品\曲风数据分析\spotify.duckdb"

# 规则允许出现的键。写错一个键名就等于静默少校验一条，所以白名单严格。
ALLOWED_RULE_KEYS = {
    "min_rows",
    "max_rows",
    "required_columns",
    "null_check_columns",
    "unique_columns",
    "column_types",
    "value_bounds",
}

# 失败码优先级：越靠前越接近根因。多项失败时取最靠前的一个作为主 code，
# 因为「列都没了」的时候再去纠结行数没有意义。
CODE_PRIORITY = (
    "INVALID_ARGS",
    "DB_ERROR",
    "SQL_ERROR",
    "COLUMN_MISMATCH",
    "TYPE_MISMATCH",
    "UNIQUE_VIOLATION",
    "ROW_COUNT_OUT_OF_RANGE",
    "NULL_CHECK_FAILED",
    "VALUE_OUT_OF_BOUNDS",
)


def _ident(name: object) -> str:
    """把标识符安全包成 DuckDB 双引号形式（内部双引号翻倍转义）。"""
    return '"' + str(name).replace('"', '""') + '"'


def _is_int(value: object) -> bool:
    # bool 是 int 的子类，但 True 当行数上限显然不是本意，要排掉。
    return isinstance(value, int) and not isinstance(value, bool)


def _jsonable(value: object) -> object:
    """把 DuckDB 可能吐出的非 JSON 原生类型转成能安全序列化的形式。

    典型是 DECIMAL：它是 decimal.Decimal，json.dumps 遇到它会走 default=str，
    于是 actual_min 变成字符串 '0.5' —— 下游拿到字符串没法直接比大小。
    这里统一转 float，让数值字段保持数值类型。
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _fail(view_name: object, code: str, detail: str, **extra) -> dict:
    return {
        "step": STEP,
        "view": view_name,
        "status": "INVALID",
        "code": code,
        "reason": detail,
        "failures": [dict({"code": code, "detail": detail}, **extra)],
    }


def create_and_validate_view(
    view_name: str,
    create_sql: str,
    validate_rules: dict,
    db_path: str | None = None,
    sample_rows: int = 0,
) -> dict:
    """创建单个视图并校验。返回契约化结论 dict，不抛异常给调用方。

    参数
    ----
    view_name        : 目标视图名
    create_sql       : CREATE OR REPLACE VIEW 语句（必须含 OR REPLACE）
    validate_rules   : 断言字典，支持 min_rows / max_rows /
                       required_columns / null_check_columns /
                       unique_columns / column_types / value_bounds
    db_path          : DuckDB 文件路径，默认 DEFAULT_DB_PATH
    sample_rows      : >0 时附带前 N 行样例，便于肉眼确认口径

    返回
    ----
    {"view": ..., "status": "VALID",   "code": "OK", "rows": N, "columns": [...], ...}
    {"view": ..., "status": "INVALID", "code": "<失败码>", "reason": "...", ...}
    """
    db_path = db_path or DEFAULT_DB_PATH

    # ── 0. 参数闸门：任一条不满足就直接返回，绝不触碰数据库 ──────────
    problems: list[str] = []

    if not isinstance(view_name, str) or not view_name.strip():
        problems.append("view_name 必须是非空字符串")

    if not isinstance(create_sql, str) or not create_sql.strip():
        problems.append("create_sql 必须是非空字符串")
    else:
        if not re.search(r"\bcreate\b", create_sql, re.I):
            problems.append("create_sql 里找不到 CREATE")
        if not re.search(r"\bor\s+replace\b", create_sql, re.I):
            problems.append(
                "create_sql 缺少 OR REPLACE —— 流水线会重跑，不带 OR REPLACE 的 "
                "CREATE VIEW 第二次执行会因「视图已存在」而失败"
            )

    if not isinstance(validate_rules, dict):
        problems.append("validate_rules 必须是字典")
    elif not validate_rules:
        problems.append(
            "validate_rules 为空 —— 没有任何断言的校验过不了闸门，至少给一条规则"
        )
    else:
        unknown = sorted(set(validate_rules) - ALLOWED_RULE_KEYS)
        if unknown:
            problems.append(
                "validate_rules 含未知键 " + ", ".join(unknown)
                + "（允许：" + ", ".join(sorted(ALLOWED_RULE_KEYS)) + "）"
                "—— 拼错的键会静默变成「没校验」，所以一律拒绝"
            )

    if not isinstance(validate_rules, dict):
        validate_rules = {}

    min_rows = validate_rules.get("min_rows")
    max_rows = validate_rules.get("max_rows")
    required_columns = validate_rules.get("required_columns") or []
    null_check_columns = validate_rules.get("null_check_columns") or []
    unique_columns = validate_rules.get("unique_columns") or []
    column_types = validate_rules.get("column_types") or {}
    value_bounds = validate_rules.get("value_bounds") or {}

    for label, value in (("min_rows", min_rows), ("max_rows", max_rows)):
        if value is not None and not _is_int(value):
            problems.append(f"{label} 必须是整数或省略，拿到 {type(value).__name__}")
    if _is_int(min_rows) and _is_int(max_rows) and min_rows > max_rows:
        problems.append(f"min_rows({min_rows}) 大于 max_rows({max_rows})，区间不成立")

    for label, value in (
        ("required_columns", required_columns),
        ("null_check_columns", null_check_columns),
        ("unique_columns", unique_columns),
    ):
        if not isinstance(value, (list, tuple)):
            problems.append(f"{label} 必须是字符串列表")
        elif not all(isinstance(c, str) for c in value):
            problems.append(f"{label} 里存在非字符串元素")

    # column_types: {列名: 期望类型字符串}，严格字面比对，故值必须是非空字符串
    if not isinstance(column_types, dict):
        problems.append("column_types 必须是字典，形如 {\"列名\": \"BIGINT\"}")
    else:
        for col, want in column_types.items():
            if not isinstance(want, str) or not want.strip():
                problems.append(
                    f"column_types[{col!r}] 必须是非空类型字符串（如 BIGINT / DOUBLE）"
                )

    # value_bounds: {列名: {"min":x, "max":y}}，区间端点可单边省略，但不能两边都省
    if not isinstance(value_bounds, dict):
        problems.append(
            "value_bounds 必须是字典，形如 {\"列名\": {\"min\": 0, \"max\": 1}}"
        )
    else:
        for col, spec in value_bounds.items():
            if not isinstance(spec, dict):
                problems.append(
                    f"value_bounds[{col!r}] 必须是字典（含 min / max），拿到 "
                    f"{type(spec).__name__}"
                )
                continue
            unknown_bd = sorted(set(spec) - {"min", "max"})
            if unknown_bd:
                problems.append(
                    f"value_bounds[{col!r}] 含未知键 " + ", ".join(unknown_bd)
                    + "（只允许 min / max）"
                )
            if "min" not in spec and "max" not in spec:
                problems.append(
                    f"value_bounds[{col!r}] 的 min 与 max 至少要给一个，"
                    "两边都不给等于没有约束"
                )
            for edge in ("min", "max"):
                v = spec.get(edge)
                if edge in spec and v is not None and not isinstance(v, (int, float)):
                    problems.append(
                        f"value_bounds[{col!r}][{edge!r}] 必须是数字，"
                        f"拿到 {type(v).__name__}"
                    )
            lo, hi = spec.get("min"), spec.get("max")
            if (
                isinstance(lo, (int, float))
                and isinstance(hi, (int, float))
                and not isinstance(lo, bool)
                and not isinstance(hi, bool)
                and lo > hi
            ):
                problems.append(
                    f"value_bounds[{col!r}] 的 min({lo}) 大于 max({hi})，区间不成立"
                )

    if problems:
        return {
            "step": STEP,
            "view": view_name,
            "status": "INVALID",
            "code": "INVALID_ARGS",
            "reason": "; ".join(problems),
            "failures": [{"code": "INVALID_ARGS", "detail": p} for p in problems],
        }

    # ── 1. 连接数据库（读写模式，建视图必须） ────────────────────────
    try:
        con = duckdb.connect(db_path)
    except Exception as exc:
        return _fail(
            view_name,
            "DB_ERROR",
            f"打不开数据库 {db_path}：{type(exc).__name__}: {exc}",
            db_path=db_path,
        )

    try:
        # ── 2. 创建视图 ──────────────────────────────────────────────
        try:
            con.execute(create_sql)
        except Exception as exc:
            return _fail(
                view_name,
                "SQL_ERROR",
                f"CREATE 语句执行失败：{type(exc).__name__}: {exc}",
                sql=create_sql.strip(),
            )

        # ── 3. 同一连接内回读：列签名 + 行数 ─────────────────────────
        # DESCRIBE 的第 2 个字段就是类型名，顺手留下供 column_types 断言用，
        # 免得为类型再查一次 information_schema。
        try:
            desc = con.execute(f"DESCRIBE {_ident(view_name)}").fetchall()
            actual_columns = [row[0] for row in desc]
            actual_types = {row[0]: str(row[1]) for row in desc}
            actual_rows = con.execute(
                f"SELECT count(*) FROM {_ident(view_name)}"
            ).fetchone()[0]
        except Exception as exc:
            return _fail(
                view_name,
                "SQL_ERROR",
                f"视图 {view_name} 建出来了，但回读不到内容：{type(exc).__name__}: {exc}",
            )

        # ── 4. 逐条断言（全部跑完，不短路） ──────────────────────────
        failures: list[dict] = []
        assertions = {
            "row_count": "skip",
            "column_set": "skip",
            "null_check": "skip",
            "unique": "skip",
            "column_type": "skip",
            "value_bounds": "skip",
        }

        # 4a. 行数是否落在闭区间内
        if min_rows is not None or max_rows is not None:
            lo = min_rows if min_rows is not None else float("-inf")
            hi = max_rows if max_rows is not None else float("inf")
            if lo <= actual_rows <= hi:
                assertions["row_count"] = "pass"
            else:
                assertions["row_count"] = "fail"
                failures.append(
                    {
                        "code": "ROW_COUNT_OUT_OF_RANGE",
                        "rule": "min_rows/max_rows",
                        "expected": [min_rows, max_rows],
                        "actual": actual_rows,
                        "detail": f"行数 {actual_rows} 不在 [{min_rows}, {max_rows}] 区间",
                    }
                )

        # 4b. required_columns 必须全部存在
        if required_columns:
            missing = [c for c in required_columns if c not in actual_columns]
            extra = [c for c in actual_columns if c not in required_columns]
            if not missing:
                assertions["column_set"] = "pass"
            else:
                assertions["column_set"] = "fail"
                failures.append(
                    {
                        "code": "COLUMN_MISMATCH",
                        "rule": "required_columns",
                        "missing_columns": missing,
                        "extra_columns": extra,
                        "detail": "缺少列: " + ", ".join(missing),
                    }
                )

        # 4c. null_check_columns 的空值数必须为 0
        if null_check_columns:
            absent = [c for c in null_check_columns if c not in actual_columns]
            if absent:
                assertions["null_check"] = "fail"
                failures.append(
                    {
                        "code": "COLUMN_MISMATCH",
                        "rule": "null_check_columns",
                        "missing_columns": absent,
                        "detail": "要查空值的列不在视图里: " + ", ".join(absent),
                    }
                )
            else:
                # 一条 SQL 查完全部列：count(*) - count(列) 即该列空值数
                select_list = ", ".join(
                    f"count(*) - count({_ident(c)}) AS {_ident(c)}"
                    for c in null_check_columns
                )
                row = con.execute(
                    f"SELECT {select_list} FROM {_ident(view_name)}"
                ).fetchone()
                null_counts = {
                    c: int(n) for c, n in zip(null_check_columns, row) if n
                }
                if not null_counts:
                    assertions["null_check"] = "pass"
                else:
                    assertions["null_check"] = "fail"
                    failures.append(
                        {
                            "code": "NULL_CHECK_FAILED",
                            "rule": "null_check_columns",
                            "null_counts": null_counts,
                            "detail": "；".join(
                                f"列 {c} 有 {n} 个空值（要求 0）"
                                for c, n in null_counts.items()
                            ),
                        }
                    )

        # 4d. unique_columns 指定的列组合必须无重复行
        # 单列走 COUNT(DISTINCT) = COUNT(*) 的快路径；多列没有对应的 DISTINCT 计数，
        # 用 GROUP BY ... HAVING count(*) > 1 找出重复组，并给出具体重复值以便定位。
        if unique_columns:
            absent = [c for c in unique_columns if c not in actual_columns]
            if absent:
                assertions["unique"] = "fail"
                failures.append(
                    {
                        "code": "COLUMN_MISMATCH",
                        "rule": "unique_columns",
                        "missing_columns": absent,
                        "detail": "要查唯一性的列不在视图里: " + ", ".join(absent),
                    }
                )
            else:
                try:
                    if len(unique_columns) == 1:
                        col = unique_columns[0]
                        distinct_n, total_n = con.execute(
                            f"SELECT count(DISTINCT {_ident(col)}), count(*) "
                            f"FROM {_ident(view_name)}"
                        ).fetchone()
                        dup_n = int(total_n) - int(distinct_n)
                        # 抽出具体的重复值，别只报个数字 —— 调用方要能直接定位。
                        # 同一列在单列分支里既是分组键又是唯一键，取值和次数都查一次。
                        dup_rows = con.execute(
                            f"SELECT {_ident(col)}, count(*) AS _dup_n "
                            f"FROM {_ident(view_name)} GROUP BY {_ident(col)} "
                            f"HAVING count(*) > 1 ORDER BY _dup_n DESC LIMIT 5"
                        ).fetchall()
                        dup_pairs = [
                            {col: _jsonable(r[0]), "重复次数": int(r[1])}
                            for r in dup_rows
                        ]
                    else:
                        cols_sql = ", ".join(_ident(c) for c in unique_columns)
                        dup_rows = con.execute(
                            f"SELECT {cols_sql}, count(*) AS _dup_n "
                            f"FROM {_ident(view_name)} GROUP BY {cols_sql} "
                            f"HAVING count(*) > 1 ORDER BY _dup_n DESC LIMIT 5"
                        ).fetchall()
                        dup_pairs = [
                            dict(zip(unique_columns, _jsonable(r[:-1])))
                            | {"重复次数": int(r[-1])}
                            for r in dup_rows
                        ]
                        # 总重复行数 = 每个重复组的 (次数 - 1) 之和
                        total_dup = con.execute(
                            f"SELECT coalesce(sum(_c - 1), 0) FROM ("
                            f"  SELECT count(*) AS _c FROM {_ident(view_name)} "
                            f"  GROUP BY {cols_sql} HAVING count(*) > 1"
                            f")"
                        ).fetchone()[0]
                        dup_n = int(total_dup)
                except Exception as exc:
                    assertions["unique"] = "fail"
                    failures.append(
                        {
                            "code": "SQL_ERROR",
                            "rule": "unique_columns",
                            "detail": f"唯一性检查执行失败：{type(exc).__name__}: {exc}",
                        }
                    )
                else:
                    if dup_n == 0:
                        assertions["unique"] = "pass"
                    else:
                        assertions["unique"] = "fail"
                        combo = " + ".join(unique_columns)
                        detail = (
                            f"列组合 ({combo}) 存在重复：{dup_n} 行属于重复组"
                        )
                        if dup_pairs:
                            detail += "；样例重复值 " + str(dup_pairs)
                        failures.append(
                            {
                                "code": "UNIQUE_VIOLATION",
                                "rule": "unique_columns",
                                "columns": list(unique_columns),
                                "duplicate_rows": dup_n,
                                "duplicates": dup_pairs,
                                "detail": detail,
                            }
                        )

        # 4e. column_types 严格字面比对 DESCRIBE 返回的类型名
        # 刻意不做等价类归一（BIGINT 与 INTEGER 不视为同类）：类型宽度变化是一个
        # 「有人动过 create_sql」的信号，闸门的职责就是抓住它，宁可误报也别静默放过。
        if column_types:
            absent = [c for c in column_types if c not in actual_columns]
            if absent:
                assertions["column_type"] = "fail"
                failures.append(
                    {
                        "code": "COLUMN_MISMATCH",
                        "rule": "column_types",
                        "missing_columns": absent,
                        "detail": "要查类型的列不在视图里: " + ", ".join(absent),
                    }
                )
            else:
                type_mismatch = {
                    c: {"expected": want, "actual": actual_types.get(c)}
                    for c, want in column_types.items()
                    if actual_types.get(c) != want
                }
                if not type_mismatch:
                    assertions["column_type"] = "pass"
                else:
                    assertions["column_type"] = "fail"
                    failures.append(
                        {
                            "code": "TYPE_MISMATCH",
                            "rule": "column_types",
                            "type_mismatch": type_mismatch,
                            "detail": "；".join(
                                f"列 {c} 类型为 {v['actual']}，期望 {v['expected']}"
                                for c, v in type_mismatch.items()
                            ),
                        }
                    )

        # 4f. value_bounds 闭区间校验，NULL 容忍（NULL 不计为越界）
        # 只查「非空且越界」的行数：NULL 表示未知，未知不等于越界；空值该不该存在
        # 归 null_check_columns 管，两个键各管一件事。
        if value_bounds:
            absent = [c for c in value_bounds if c not in actual_columns]
            if absent:
                assertions["value_bounds"] = "fail"
                failures.append(
                    {
                        "code": "COLUMN_MISMATCH",
                        "rule": "value_bounds",
                        "missing_columns": absent,
                        "detail": "要查值域的列不在视图里: " + ", ".join(absent),
                    }
                )
            else:
                bounds_violations: dict[str, dict] = {}
                bound_errors: list[str] = []
                for col, spec in value_bounds.items():
                    lo, hi = spec.get("min"), spec.get("max")
                    conds = []
                    if lo is not None:
                        conds.append(f"{_ident(col)} < {lo!r}")
                    if hi is not None:
                        conds.append(f"{_ident(col)} > {hi!r}")
                    if not conds:
                        continue
                    where = " OR ".join(conds)
                    try:
                        # 只数「越界」的，NULL 自动被 OR 判为 NULL 而不计入
                        bad_n, bad_min, bad_max = con.execute(
                            f"SELECT count(*) FILTER (WHERE {where}), "
                            f"min({_ident(col)}), max({_ident(col)}) "
                            f"FROM {_ident(view_name)}"
                        ).fetchone()
                    except Exception as exc:
                        bound_errors.append(
                            f"列 {col} 值域检查执行失败：{type(exc).__name__}: {exc}"
                        )
                        continue
                    if bad_n:
                        bounds_violations[col] = {
                            "expected": {"min": lo, "max": hi},
                            "actual_min": _jsonable(bad_min),
                            "actual_max": _jsonable(bad_max),
                            "violating_rows": int(bad_n),
                        }
                if bound_errors:
                    assertions["value_bounds"] = "fail"
                    failures.append(
                        {
                            "code": "SQL_ERROR",
                            "rule": "value_bounds",
                            "detail": "；".join(bound_errors),
                        }
                    )
                if bounds_violations:
                    assertions["value_bounds"] = "fail"
                    failures.append(
                        {
                            "code": "VALUE_OUT_OF_BOUNDS",
                            "rule": "value_bounds",
                            "violations": bounds_violations,
                            "detail": "；".join(
                                f"列 {c} 有 {v['violating_rows']} 行越界"
                                f"（实际范围 [{v['actual_min']}, {v['actual_max']}]，"
                                f"要求 [{v['expected']['min']}, {v['expected']['max']}]）"
                                for c, v in bounds_violations.items()
                            ),
                        }
                    )
                elif not bound_errors:
                    assertions["value_bounds"] = "pass"

        # ── 5. 组装结论 ──────────────────────────────────────────────
        result: dict = {
            "step": STEP,
            "view": view_name,
            "status": "VALID" if not failures else "INVALID",
            "code": "OK"
            if not failures
            else min(
                (f["code"] for f in failures),
                key=lambda c: CODE_PRIORITY.index(c)
                if c in CODE_PRIORITY
                else len(CODE_PRIORITY),
            ),
            "rows": actual_rows,
            "columns": actual_columns,
            "assertions": assertions,
        }

        if failures:
            failures.sort(
                key=lambda f: CODE_PRIORITY.index(f["code"])
                if f["code"] in CODE_PRIORITY
                else len(CODE_PRIORITY)
            )
            result["reason"] = "; ".join(f["detail"] for f in failures)
            result["failures"] = failures

        # ── 6. 可选：取前 N 行样例 ──────────────────────────────────
        if _is_int(sample_rows) and sample_rows > 0:
            try:
                cur = con.execute(
                    f"SELECT * FROM {_ident(view_name)} LIMIT {int(sample_rows)}"
                )
                cols = [d[0] for d in cur.description]
                result["sample"] = [
                    {k: _jsonable(v) for k, v in zip(cols, r)} for r in cur.fetchall()
                ]
            except Exception as exc:
                result["sample_error"] = f"{type(exc).__name__}: {exc}"

        return result

    finally:
        # 无论成功失败都关掉连接，避免文件句柄残留挡住下一次写入
        try:
            con.close()
        except Exception:
            pass


def _read_text(source: str) -> str:
    """读文本。'-' 表示 stdin，且按 UTF-8 解，避开 Windows 默认 GBK。"""
    if source == "-":
        return sys.stdin.buffer.read().decode("utf-8")
    return Path(source).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        prog="create_and_validate_view",
        description="在 DuckDB 上创建单个视图并校验，输出契约化 JSON。",
    )
    parser.add_argument(
        "--json",
        dest="json_source",
        metavar="<file|->",
        help="一次性传完整入参的 JSON 文件；'-' 表示从 stdin 读。SQL 含引号/换行时首选这种方式。",
    )
    parser.add_argument("--view-name", help="视图名")
    parser.add_argument("--create-sql", help="CREATE OR REPLACE VIEW 语句本体")
    parser.add_argument("--create-sql-file", help="从文件读 CREATE 语句")
    parser.add_argument("--rules-json", help="断言字典的 JSON 字符串")
    parser.add_argument("--rules-file", help="从文件读断言字典 JSON")
    parser.add_argument("--db", help=f"DuckDB 路径，默认 {DEFAULT_DB_PATH}")
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=0,
        help=">0 时在结论里附带前 N 行样例",
    )

    args = parser.parse_args(argv)

    # ── 组装入参 ────────────────────────────────────────────────────
    if args.json_source:
        try:
            payload = json.loads(_read_text(args.json_source))
        except FileNotFoundError:
            payload = None
            err = f"入参文件不存在：{args.json_source}"
        except json.JSONDecodeError as exc:
            payload = None
            err = f"入参 JSON 解析失败：{exc}"
        else:
            err = None
        if err:
            result = _fail(None, "INVALID_ARGS", err)
            print(json.dumps(result, ensure_ascii=False, default=str))
            return 1

        view_name = payload.get("view_name")
        create_sql = payload.get("create_sql")
        validate_rules = payload.get("validate_rules")
        db_path = args.db or payload.get("db_path")
        sample_rows = args.sample_rows or payload.get("sample_rows") or 0
    else:
        view_name = args.view_name
        if args.create_sql_file:
            try:
                create_sql = _read_text(args.create_sql_file)
            except FileNotFoundError:
                result = _fail(view_name, "INVALID_ARGS", f"SQL 文件不存在：{args.create_sql_file}")
                print(json.dumps(result, ensure_ascii=False, default=str))
                return 1
        else:
            create_sql = args.create_sql

        raw_rules = args.rules_json
        if raw_rules is None and args.rules_file:
            try:
                raw_rules = _read_text(args.rules_file)
            except FileNotFoundError:
                result = _fail(view_name, "INVALID_ARGS", f"规则文件不存在：{args.rules_file}")
                print(json.dumps(result, ensure_ascii=False, default=str))
                return 1
        if raw_rules is None:
            validate_rules = None
        else:
            try:
                validate_rules = json.loads(raw_rules)
            except json.JSONDecodeError as exc:
                result = _fail(view_name, "INVALID_ARGS", f"规则 JSON 解析失败：{exc}")
                print(json.dumps(result, ensure_ascii=False, default=str))
                return 1

        db_path = args.db
        sample_rows = args.sample_rows

    result = create_and_validate_view(
        view_name,
        create_sql,
        validate_rules,
        db_path=db_path,
        sample_rows=sample_rows,
    )
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result.get("status") == "VALID" else 1


if __name__ == "__main__":
    sys.exit(main())
