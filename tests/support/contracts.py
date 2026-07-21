"""为全部算符提供可通过生产模型校验的最小规范定义。"""

from copy import deepcopy
from typing import Any, get_args

from pydantic_core import PydanticUndefined

from core.operators import Derivative
from core.operators.base import CrossSectionOperator, DirectOperator


def operation_name(model: type[Derivative]) -> str:
    """读取具体算符类声明的唯一 op。"""
    return get_args(model.model_fields["op"].annotation)[0]


def _field_value(name: str) -> Any:
    """返回对应字段的规范测试操作数。"""
    values: dict[str, Any] = {
        "by": "industry",
        "col": "x",
        "condition": "flag",
        "controls": ["industry", "size"],
        "cols": ["x", "y", 1.0],
        "if_false": "y",
        "if_true": "x",
        "left": "x",
        "right": "y",
        "target": "x",
    }
    return values.get(name, name)


def _required_parameter(operation: str, name: str, annotation: Any) -> Any:
    """为没有默认值的参数提供满足边界约束的规范值。"""
    if name in {"time_period", "window"}:
        return 5
    if name == "value":
        return 3.5
    if name == "lower":
        return -1.0
    if name == "upper":
        return 1.0
    if name == "n":
        return 2
    if name == "pct":
        return 0.4
    if name == "dtype":
        return "double"
    if name == "q":
        return 4 if annotation is int else 0.4
    if name == "values":
        return [1, 3, None]
    if name == "old":
        return [1, 2]
    if name == "new":
        return [10, 20]
    raise AssertionError(f"{operation} 缺少规范参数 {name}")


def canonical_definition(operation: str) -> dict[str, Any]:
    """根据具体模型生成一个完整且有效的 DSL 定义。"""
    model = Derivative.operators[operation]
    fields_type = model.model_fields["fields"].annotation
    params_type = model.model_fields["params"].annotation
    fields = {name: _field_value(name) for name in fields_type.model_fields}
    params: dict[str, Any] = {}
    for name, field in params_type.model_fields.items():
        if field.default is PydanticUndefined and field.default_factory is None:
            params[name] = _required_parameter(operation, name, field.annotation)

    if operation == "unary.clip":
        params.update(lower=-1.0, upper=1.0)
    if "ewm_" in operation:
        params["span"] = 5.0

    if issubclass(model, DirectOperator):
        node_type = "DIRECT"
    elif issubclass(model, CrossSectionOperator):
        node_type = "CS"
    else:
        node_type = "TS"
    definition: dict[str, Any] = {
        "type": node_type,
        "op": operation,
        "fields": fields,
        "params": params,
    }
    if node_type != "DIRECT":
        definition["on"] = "active"
    return definition


def changed_params(operation: str, **changes: Any) -> dict[str, Any]:
    """复制规范定义并替换 params，供边界校验测试使用。"""
    definition = deepcopy(canonical_definition(operation))
    definition["params"].update(changes)
    return definition


ALL_OPERATIONS = tuple(sorted(Derivative.operators))


__all__ = [
    "ALL_OPERATIONS",
    "canonical_definition",
    "changed_params",
    "operation_name",
]
