"""根据已导入的算符模型生成 DolphinDB 运行脚本。"""

from pathlib import Path
from typing import Type, get_args

from core.query.dolphindb.function import (
    DolphinDBFunction,
    collect_functions,
    render_functions,
)
from core.query.dolphindb.runtime import (
    DERIVE_ENTRY_FUNCTIONS,
    DERIVE_HELPER_FUNCTIONS,
    TOOL_FUNCTIONS,
)
from core.query.operator import Derivative
from core.query.operator.base import (
    CrossSectionOperator,
    DirectOperator,
    OperatorBase,
    TimeSeriesOperator,
)
from core.query.operator.fields import ControlsFields, GroupedFields
from core.utils import logger

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "output"
SCRIPT_PATH = OUTPUT_DIR / "operators.dos"


def _operation_name(model: Type[OperatorBase]) -> str:
    """读取算符模型声明的唯一 DSL 名称。"""
    return get_args(model.model_fields["op"].annotation)[0]


def _argument_names(model: Type[OperatorBase]) -> tuple[list[str], list[str]]:
    """按函数签名拆分算符操作数和普通参数。"""
    fields_type = model.model_fields["fields"].annotation
    params_type = model.model_fields["params"].annotation
    field_names = [name for name in fields_type.model_fields if name != "by"]
    parameter_names = list(params_type.model_fields)
    operands = [name for name in model.function.parameters if name in field_names]
    parameters = [name for name in model.function.parameters if name in parameter_names]
    return operands, parameters


def _function_call(model: Type[OperatorBase]) -> str:
    """生成 DIRECT 算符的普通函数调用。"""
    operands, parameters = _argument_names(model)
    arguments = [
        *(f'fields["{name}"]' for name in operands),
        *(f'params["{name}"]' for name in parameters),
    ]
    return f"{model.function.name}({', '.join(arguments)})"


def _partial_function(model: Type[OperatorBase]) -> str:
    """生成保留操作数位置的 DolphinDB 部分应用。"""
    operands, parameters = _argument_names(model)
    if not parameters:
        return model.function.name
    params_type = model.model_fields["params"].annotation
    values = ", ".join(
        _bound_parameter(name, params_type.model_fields[name].annotation)
        for name in parameters
    )
    return f"{model.function.name}{{{',' * len(operands)} {values}}}"


def _bound_parameter(name: str, annotation: object) -> str:
    """为部分应用中的可空参数补充类型，避免 NULL 被解释为未绑定占位符。"""
    expression = f'params["{name}"]'
    members = get_args(annotation)
    if type(None) not in members:
        return expression
    value_type = next(member for member in members if member is not type(None))
    cast = {bool: "bool", float: "double", int: "int", str: "string"}[value_type]
    return f"{cast}({expression})"


def _required_operands(model: Type[OperatorBase]) -> list[str]:
    """生成 TS/CS 分支中的等长向量读取语句。"""
    operands, _ = _argument_names(model)
    return [
        f'{name} = require_vector(fields["{name}"], n, op + ".fields.{name}")'
        for name in operands
    ]


def _operand_collection(model: Type[OperatorBase]) -> str:
    """生成传给上下文执行函数的操作数集合。"""
    operands, _ = _argument_names(model)
    if len(operands) == 1:
        return f"enlist({operands[0]})"
    return f"({', '.join(operands)})"


def _empty_result(model: Type[OperatorBase]) -> str:
    """根据静态输出类型生成零行结果；ANY 输出沿用首个操作数类型。"""
    if model.output_kind == "BOOL":
        return "bool([])"
    if model.output_kind == "NUMBER":
        return "double([])"
    operands, _ = _argument_names(model)
    return f"array(type({operands[0]}), 0)"


def _render_function(name: str, parameters: str, lines: list[str]) -> DolphinDBFunction:
    """把函数体行渲染成 DolphinDBFunction。"""
    body = "\n".join(f"    {line}" if line else "" for line in lines)
    return DolphinDBFunction(f"def {name}({parameters}) {{\n{body}\n}}")


def _direct_evaluator(models: list[Type[OperatorBase]]) -> DolphinDBFunction:
    """生成 DIRECT 算符分发函数。"""
    lines = [
        "// 解析 DIRECT 节点的 fields 和 params，并调用匹配的逐行算符函数。",
        'op = node["op"]',
        "fields = evaluate_fields(evaluator, source, definitions, cache, states, node[\"fields\"])",
        'params = node["params"]',
        "",
    ]
    for model in models:
        operation = _operation_name(model)
        lines.append(f'if (op == "{operation}") {{')
        lines.append(f"    return {_function_call(model)}")
        lines.append("}")
    lines.append('throw "未实现 DIRECT 算符 " + op')
    return _render_function(
        "evaluate_direct",
        "evaluator, source, definitions, mutable cache, mutable states, node",
        lines,
    )


def _time_series_evaluator(models: list[Type[OperatorBase]]) -> DolphinDBFunction:
    """生成 TS 算符分发函数。"""
    lines = [
        "// 解析 TS 节点，校验操作数后交由按 code、time 组织的时序执行上下文计算。",
        'op = node["op"]',
        "fields = evaluate_fields(evaluator, source, definitions, cache, states, node[\"fields\"])",
        'params = node["params"]',
        "n = source.rows()",
        'code = require_column(source, "code", op)',
        'time = require_column(source, "time", op)',
        'on = evaluate_operand(evaluator, source, definitions, cache, states, node["on"])',
        "",
    ]
    for model in models:
        operation = _operation_name(model)
        lines.append(f'if (op == "{operation}") {{')
        lines.extend(f"    {line}" for line in _required_operands(model))
        lines.append(f"    handler = {_partial_function(model)}")
        lines.append(
            f"    return apply_time_series(handler, {_operand_collection(model)}, on, code, time, {_empty_result(model)})"
        )
        lines.append("}")
    lines.append('throw "未实现 TS 算符 " + op')
    return _render_function(
        "evaluate_time_series",
        "evaluator, source, definitions, mutable cache, mutable states, node",
        lines,
    )


def _controls_branch(model: Type[OperatorBase]) -> list[str]:
    """生成 controls 字段的按日执行分支。"""
    return [
        'target = require_vector(fields["target"], n, op + ".fields.target")',
        'control_values = fields["controls"]',
        "normalized_controls = array(ANY, 0)",
        "for (index in 0..(size(control_values) - 1)) {",
        "    normalized_controls.append!(",
        "        require_vector(",
        "            control_values[index],",
        "            n,",
        '            op + ".fields.controls[" + string(index) + "]"',
        "        )",
        "    )",
        "}",
        "controls = build_control_table(normalized_controls)",
        f"handler = {_partial_function(model)}",
        "return apply_controlled_cross_section(handler, target, controls, on, time)",
    ]


def _grouped_branch(model: Type[OperatorBase]) -> list[str]:
    """生成 grouped 字段的二级分组执行分支。"""
    return [
        *_required_operands(model),
        'by = require_vector(fields["by"], n, op + ".fields.by")',
        f"handler = {_partial_function(model)}",
        (
            f"return apply_grouped_cross_section(handler, {_operand_collection(model)}, "
            f"on, time, by, {_empty_result(model)})"
        ),
    ]


def _cross_section_evaluator(models: list[Type[OperatorBase]]) -> DolphinDBFunction:
    """生成 CS 算符分发函数。"""
    lines = [
        "// 解析 CS 节点，并根据普通、分组或控制变量字段选择对应截面执行上下文。",
        'op = node["op"]',
        "fields = evaluate_fields(evaluator, source, definitions, cache, states, node[\"fields\"])",
        'params = node["params"]',
        "n = source.rows()",
        'time = require_column(source, "time", op)',
        'on = evaluate_operand(evaluator, source, definitions, cache, states, node["on"])',
        "",
    ]
    for model in models:
        operation = _operation_name(model)
        fields_type = model.model_fields["fields"].annotation
        lines.append(f'if (op == "{operation}") {{')
        if fields_type is ControlsFields:
            branch = _controls_branch(model)
        elif fields_type is GroupedFields:
            branch = _grouped_branch(model)
        else:
            branch = [
                *_required_operands(model),
                f"handler = {_partial_function(model)}",
                (
                    f"return apply_cross_section(handler, {_operand_collection(model)}, "
                    f"on, time, {_empty_result(model)})"
                ),
            ]
        lines.extend(f"    {line}" for line in branch)
        lines.append("}")
    lines.append('throw "未实现 CS 算符 " + op')
    return _render_function(
        "evaluate_cross_section",
        "evaluator, source, definitions, mutable cache, mutable states, node",
        lines,
    )


def _models_by_type() -> tuple[
    list[Type[OperatorBase]],
    list[Type[OperatorBase]],
    list[Type[OperatorBase]],
]:
    """按 DIRECT、TS、CS 拆分已登记算符。"""
    models = sorted(Derivative.operators.values(), key=lambda model: model.function.name)
    direct = [model for model in models if issubclass(model, DirectOperator)]
    time_series = [model for model in models if issubclass(model, TimeSeriesOperator)]
    cross_section = [model for model in models if issubclass(model, CrossSectionOperator)]
    return direct, time_series, cross_section


def evaluator_functions() -> tuple[DolphinDBFunction, DolphinDBFunction, DolphinDBFunction]:
    """根据自动登记的模型生成三类执行分发函数。"""
    direct, time_series, cross_section = _models_by_type()
    return (
        _direct_evaluator(direct),
        _time_series_evaluator(time_series),
        _cross_section_evaluator(cross_section),
    )


def _render_section(
        title: str,
        description: str,
        content: str,
) -> str:
    """渲染一个具名 DOS 函数章节。"""
    return f"// {title}\n// {description}\n\n{content.rstrip()}\n\n"


def build_script() -> str:
    """按工具、三类算符和 derive 执行层生成完整脚本。"""
    direct_models, time_series_models, cross_section_models = _models_by_type()
    direct_functions = tuple(model.function for model in direct_models)
    time_series_functions = tuple(model.function for model in time_series_models)
    cross_section_functions = tuple(model.function for model in cross_section_models)
    operator_functions = (
        *direct_functions,
        *time_series_functions,
        *cross_section_functions,
    )
    derive = (
        *DERIVE_HELPER_FUNCTIONS,
        *evaluator_functions(),
        *DERIVE_ENTRY_FUNCTIONS,
    )
    operator_names = {function.name for function in operator_functions}
    derive_names = {function.name for function in derive}
    tools = tuple(
        function
        for function in collect_functions(
            (*operator_functions, *TOOL_FUNCTIONS, *derive)
        )
        if function.name not in operator_names
        and function.name not in derive_names
    )
    header = (
        "use ta\n\n"
        "// 此文件由 core.query.dolphindb.script 生成，请修改 Python 中的函数定义。\n"
        "// on、code、time、分组、排序和结果回填仅由 derive 执行层处理。\n\n"
    )
    script = "".join(
        (
            header,
            _render_section(
                "工具函数",
                "提供数据形态、数值、窗口、截面及执行上下文使用的共享函数。",
                render_functions(tools),
            ),
            _render_section(
                "DIRECT operators",
                "仅根据 fields 与 params 逐行计算，不读取 code、time 或 on。",
                render_functions(direct_functions),
            ),
            _render_section(
                "TS operators",
                "在单个 code 的有序时序内计算，分组、筛选和回填由 derive 负责。",
                render_functions(time_series_functions),
            ),
            _render_section(
                "CS operators",
                "在单个交易日的截面内计算，筛选、分组和回填由 derive 负责。",
                render_functions(cross_section_functions),
            ),
            _render_section(
                "derive",
                "递归解析 DSL、缓存命名因子，并统一处理 on、分组、排序及结果回填。",
                render_functions(derive),
            ),
        )
    )
    return script.rstrip() + "\n"


def write_script(path: Path = SCRIPT_PATH) -> Path:
    """将完整脚本写入指定路径。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_script(), encoding="utf-8", newline="\n")
    logger.success(f"DolphinDB DSL 脚本已生成：{path}")
    return path


if __name__ == "__main__":
    print(write_script())

__all__ = [
    "OUTPUT_DIR",
    "SCRIPT_PATH",
    "build_script",
    "evaluator_functions",
    "write_script",
]
