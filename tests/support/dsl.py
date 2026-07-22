"""构造并执行完整 JSON DSL，所有结果都经过生产入口模型校验。"""

import json
from typing import Any

import pandas as pd

from core.query.operator import Derivative


def node(
    node_type: str,
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
    *,
    on: object | None = None,
) -> dict[str, Any]:
    """构造一个未校验 DSL 节点。"""
    result: dict[str, Any] = {
        "type": node_type,
        "op": operation,
        "fields": fields,
        "params": {} if params is None else params,
    }
    if node_type != "DIRECT":
        result["on"] = on
    return result


def direct(
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 DIRECT 节点。"""
    return node("DIRECT", operation, fields, params)


def time_series(
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
    *,
    on: object | None = None,
) -> dict[str, Any]:
    """构造 TS 节点。"""
    return node("TS", operation, fields, params, on=on)


def cross_section(
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
    *,
    on: object | None = None,
) -> dict[str, Any]:
    """构造 CS 节点。"""
    return node("CS", operation, fields, params, on=on)


TRUE_NODE = direct("nullary.true", {})


def validate_definitions(
    definitions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """通过生产入口校验全部定义，并展开默认参数。"""
    return {
        name: Derivative.model_validate(definition).model_dump(mode="json")
        for name, definition in definitions.items()
    }


def compute_factors(
    session: Any,
    source: pd.DataFrame,
    definitions: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """上传输入表，并经 JSON 解析和生产执行器计算全部命名因子。"""
    normalized = source.copy()
    if "time" in normalized:
        normalized["time"] = pd.to_datetime(normalized["time"])
    payload = json.dumps(
        validate_definitions(definitions),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    session.upload({"test_dsl_source": normalized})
    quoted = json.dumps(payload, ensure_ascii=False)
    return session.run(
        f"compute_factors(test_dsl_source, fromStdJson({quoted}))"
    )


def run_uploaded(
    session: Any,
    expression: str,
    **values: Any,
) -> Any:
    """上传具名输入后执行一条 DolphinDB 表达式。"""
    if values:
        session.upload(values)
    return session.run(expression)


__all__ = [
    "TRUE_NODE",
    "compute_factors",
    "cross_section",
    "direct",
    "node",
    "run_uploaded",
    "time_series",
    "validate_definitions",
]
