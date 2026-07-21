"""验证全部算符模型、严格 JSON 规则和自动登记约束。"""

from copy import deepcopy
import math
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, ValidationError
import pytest

from core.dolphindb import DolphinDBFunction
from core.operators import Derivative
from core.operators.base import DirectOperator, OperatorBase
from core.operators.fields import StrictModel, UnaryFields
from tests.support.contracts import (
    ALL_OPERATIONS,
    canonical_definition,
    changed_params,
    operation_name,
)
from tests.support.dsl import direct, time_series


@pytest.mark.parametrize("operation", ALL_OPERATIONS)
def test_every_operator_accepts_its_canonical_json(operation: str) -> None:
    """每个已登记算符都必须能经统一入口构造成自己的具体模型。"""
    definition = canonical_definition(operation)
    result = Derivative.model_validate(definition)
    assert type(result) is Derivative.operators[operation]
    assert result.op == operation
    assert result.model_dump(mode="json")["params"] == result.params.model_dump(
        mode="json"
    )


def test_operator_manifest_and_model_structure_are_complete() -> None:
    """每个算符必须独占模型文件，并完整声明字段、参数、函数和文档。"""
    assert len(ALL_OPERATIONS) == 231
    function_names: set[str] = set()
    for operation, model in Derivative.operators.items():
        assert operation_name(model) == operation
        assert model.function.name not in function_names
        function_names.add(model.function.name)
        assert model.model_fields["fields"].description
        assert model.model_fields["params"].description
        assert model.function.definition.startswith("def ")
        assert "Parameters" in model.function.definition
        assert "Returns" in model.function.definition
        assert "NULL 处理" in model.function.definition
        assert "Examples" in model.function.definition
        assert model.__module__ == model.model_fields["params"].annotation.__module__


@pytest.mark.parametrize("value", [None, 1, "x", [], object()])
def test_derivative_rejects_non_object_inputs(value: Any) -> None:
    """统一入口只接受字典或已经校验的 Derivative。"""
    with pytest.raises(ValidationError, match="Derivative 必须是 JSON 对象"):
        Derivative.model_validate(value)


def test_derivative_returns_an_existing_instance_without_revalidation() -> None:
    """已经校验的实例再次进入统一入口时应保持对象身份。"""
    instance = Derivative.model_validate(canonical_definition("binary.add"))
    assert Derivative.model_validate(instance) is instance


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        ({}, "Derivative.op 为必填字符串"),
        ({"op": 1}, "Derivative.op 为必填字符串"),
        ({"op": "missing.operator"}, "不存在算符"),
    ],
)
def test_derivative_reports_dispatch_errors(
    definition: dict[str, Any],
    message: str,
) -> None:
    """缺失、错误类型和未知 op 应给出不同诊断。"""
    with pytest.raises(ValidationError, match=message):
        Derivative.model_validate(definition)


def test_models_forbid_extra_fields_and_implicit_coercion() -> None:
    """所有模型都应禁止额外字段和字符串到数字的隐式转换。"""
    extra = canonical_definition("binary.add")
    extra["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Derivative.model_validate(extra)

    wrong_type = canonical_definition("unary.rolling_mean")
    wrong_type["params"]["window"] = "5"
    with pytest.raises(ValidationError, match="valid integer"):
        Derivative.model_validate(wrong_type)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_strict_model_rejects_non_finite_scalars(value: float) -> None:
    """任何层级的非有限浮点数都不能进入 DSL。"""
    definition = canonical_definition("nullary.literal")
    definition["params"]["value"] = value
    with pytest.raises(ValidationError, match="不能是 NaN 或正负无穷"):
        Derivative.model_validate(definition)


def test_strict_model_recurses_into_models_lists_and_tuples() -> None:
    """非有限数检查必须覆盖嵌套模型、列表和元组三种容器。"""

    class Child(StrictModel):
        value: float = Field(...)

    class Container(StrictModel):
        child: Child = Field(...)
        values: list[float] = Field(...)
        pair: tuple[float, ...] = Field(...)

    with pytest.raises(ValueError, match="child.value"):
        Container.model_construct(
            child=Child.model_construct(value=math.inf),
            values=[1.0],
            pair=(1.0,),
        ).reject_non_finite_numbers()
    with pytest.raises(ValueError, match=r"values\[1\]"):
        Container.model_construct(
            child=Child(value=1.0),
            values=[1.0, math.nan],
            pair=(1.0,),
        ).reject_non_finite_numbers()
    with pytest.raises(ValueError, match=r"pair\[1\]"):
        Container.model_construct(
            child=Child(value=1.0),
            values=[1.0],
            pair=(1.0, -math.inf),
        ).reject_non_finite_numbers()


def test_on_accepts_bool_columns_and_bool_expressions() -> None:
    """on 可以是列名或静态返回 BOOL 的嵌套表达式。"""
    column = canonical_definition("unary.rolling_mean")
    assert Derivative.model_validate(column).on == "active"

    comparisons = [
        direct("binary.gt", {"left": "x", "right": 0.0}),
        direct("unary.cast", {"col": "x"}, {"dtype": "bool"}),
        direct("nullary.literal", {}, {"value": 1, "dtype": "bool"}),
        direct("nullary.literal", {}, {"value": True}),
    ]
    for on in comparisons:
        definition = time_series(
            "unary.rolling_mean",
            {"col": "x"},
            {"window": 3},
            on=on,
        )
        assert isinstance(Derivative.model_validate(definition).on, Derivative)


def test_on_rejects_non_bool_nested_expressions() -> None:
    """静态数值表达式不能作为 TS/CS 的 on。"""
    definition = time_series(
        "unary.rolling_mean",
        {"col": "x"},
        {"window": 3},
        on=direct("binary.add", {"left": "x", "right": 1.0}),
    )
    with pytest.raises(ValidationError, match="必须返回 BOOL"):
        Derivative.model_validate(definition)


EWM_OPERATIONS = (
    "binary.ewm_corr",
    "binary.ewm_cov",
    "unary.ewm_mean",
    "unary.ewm_std",
    "unary.ewm_var",
)


@pytest.mark.parametrize("operation", EWM_OPERATIONS)
def test_ewm_requires_exactly_one_decay_parameter(operation: str) -> None:
    """每个 EWM 模型都应拒绝零个或多个衰减参数。"""
    with pytest.raises(ValidationError, match="必须且只能提供一个"):
        Derivative.model_validate(changed_params(operation, span=None))
    with pytest.raises(ValidationError, match="必须且只能提供一个"):
        Derivative.model_validate(
            changed_params(operation, span=3.0, alpha=0.5)
        )
    for parameters in (
        {"com": 2.0, "span": None},
        {"half_life": 2.0, "span": None},
        {"alpha": 0.4, "span": None},
    ):
        assert Derivative.model_validate(
            changed_params(operation, **parameters)
        ).op == operation


WINDOW_VALIDATORS = tuple(
    operation
    for operation in ALL_OPERATIONS
    if "window"
    in Derivative.operators[operation]
    .model_fields["params"]
    .annotation.model_fields
    and "min_periods"
    in Derivative.operators[operation]
    .model_fields["params"]
    .annotation.model_fields
)


@pytest.mark.parametrize("operation", WINDOW_VALIDATORS)
def test_min_periods_cannot_exceed_window(operation: str) -> None:
    """所有滚动模型都必须执行相同的窗口边界校验。"""
    with pytest.raises(ValidationError, match="min_periods 不能大于"):
        Derivative.model_validate(
            changed_params(operation, window=4, min_periods=5)
        )


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        (changed_params("unary.between", lower=2.0, upper=1.0), "lower 不能大于"),
        (changed_params("unary.clip", lower=None, upper=None), "至少提供一个"),
        (changed_params("unary.clip", lower=2.0, upper=1.0), "lower 不能大于"),
        (changed_params("unary.replace", old=[1], new=[2, 3]), "必须等长"),
        (changed_params("unary.winsorize", lower=0.8), "less than 0.5"),
        (changed_params("talib.apo", fast_period=5, slow_period=5), "fast_period 必须小于"),
        (changed_params("talib.ppo", fast_period=6, slow_period=5), "fast_period 必须小于"),
        (changed_params("talib.macd", fast_period=8, slow_period=8), "fast_period 必须小于"),
        (changed_params("talib.ultOsc", period1=7, period2=7, period3=20), "必须严格递增"),
    ],
)
def test_cross_parameter_validation(
    definition: dict[str, Any],
    message: str,
) -> None:
    """跨参数约束应在构造阶段失败并指出具体关系。"""
    with pytest.raises(ValidationError, match=message):
        Derivative.model_validate(definition)


@pytest.mark.parametrize(
    "operation",
    [
        "talib.adx",
        "talib.adxr",
        "talib.aroon",
        "talib.aroonOsc",
        "talib.bBands",
        "talib.cci",
        "talib.dx",
        "talib.linearreg",
        "talib.linearreg_angle",
        "talib.linearreg_intercept",
        "talib.linearreg_slope",
        "talib.mfi",
        "talib.midPoint",
        "talib.midPrice",
        "talib.rsi",
        "talib.stddev",
        "talib.tsf",
        "talib.willr",
    ],
)
def test_talib_period_one_is_rejected_where_backend_does_not_support_it(
    operation: str,
) -> None:
    """底层 TA-Lib 拒绝的一期窗口必须在模型构造阶段失败。"""
    with pytest.raises(ValidationError):
        Derivative.model_validate(changed_params(operation, time_period=1))


@pytest.mark.parametrize("operation", ["talib.apo", "talib.ppo", "talib.macd"])
def test_talib_fast_period_one_is_rejected(operation: str) -> None:
    """振荡器不允许把 TA-Lib 不支持的一期均线作为快线。"""
    with pytest.raises(ValidationError):
        Derivative.model_validate(
            changed_params(operation, fast_period=1, slow_period=3)
        )


@pytest.mark.parametrize("operation", ["talib.apo", "talib.ppo", "talib.ma", "talib.bBands"])
def test_talib_mama_type_is_rejected_before_dolphindb(operation: str) -> None:
    """当前 DolphinDB 版本不支持的 MAMA 类型 7 不得进入执行层。"""
    with pytest.raises(ValidationError):
        Derivative.model_validate(changed_params(operation, ma_type=7))


def test_clip_accepts_each_single_sided_bound() -> None:
    """clip 可以只提供下界或只提供上界。"""
    assert Derivative.model_validate(
        changed_params("unary.clip", lower=-1.0, upper=None)
    )
    assert Derivative.model_validate(
        changed_params("unary.clip", lower=None, upper=1.0)
    )


@pytest.mark.parametrize(
    "parameters",
    [
        {"value": 1},
        {"value": None, "dtype": "double"},
        {"value": "2024-02-29", "dtype": "date"},
        {"value": "2024-02-29T09:30:00", "dtype": "timestamp"},
        {"value": "2024-02-29T09:30:00.123", "dtype": "timestamp"},
    ],
)
def test_literal_accepts_unambiguous_values(parameters: dict[str, Any]) -> None:
    """普通值、显式 NULL 和合法日期时间字面量应通过。"""
    definition = canonical_definition("nullary.literal")
    definition["params"] = parameters
    assert Derivative.model_validate(definition)


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"value": None}, "NULL 字面量必须指定"),
        ({"value": 20240101, "dtype": "date"}, "必须是字符串"),
        ({"value": "2024/01/01", "dtype": "date"}, "YYYY-MM-DD"),
        ({"value": "2024-02-30", "dtype": "date"}, "YYYY-MM-DD"),
        ({"value": 1, "dtype": "timestamp"}, "必须是字符串"),
        ({"value": "2024-01-01 09:30:00", "dtype": "timestamp"}, "YYYY-MM-DDTHH"),
        ({"value": "2024-13-01T09:30:00", "dtype": "timestamp"}, "ISO 8601"),
        ({"value": "2024-01-01T09:30:00+08:00", "dtype": "timestamp"}, "不能包含时区"),
    ],
)
def test_literal_rejects_ambiguous_or_invalid_values(
    parameters: dict[str, Any],
    message: str,
) -> None:
    """NULL、日期格式、无效日期和时区错误应有独立诊断。"""
    definition = canonical_definition("nullary.literal")
    definition["params"] = parameters
    with pytest.raises(ValidationError, match=message):
        Derivative.model_validate(definition)


def _params_model(name: str, *, base: type[StrictModel] = StrictModel) -> type[StrictModel]:
    """创建供自动登记约束测试使用的参数模型。"""
    return type(
        name,
        (base,),
        {
            "__module__": __name__,
            "__annotations__": {"amount": int},
            "amount": Field(default=1),
        },
    )


def _operator_class(
    name: str,
    operation: str,
    *,
    base: type[OperatorBase] = DirectOperator,
    fields_type: Any = UnaryFields,
    params_type: Any | None = None,
    operation_annotation: Any | None = None,
    function: Any | None = None,
    type_annotation: Any | None = None,
) -> type[OperatorBase]:
    """动态创建一个算符类，以逐个触发自动登记的结构检查。"""
    params = params_type or _params_model(name.removesuffix("Operator") + "Params")
    expected = f"direct_{operation.replace('.', '_')}"
    annotations: dict[str, Any] = {
        "op": Literal[operation] if operation_annotation is None else operation_annotation,
        "fields": fields_type,
        "params": params,
    }
    namespace: dict[str, Any] = {
        "__module__": __name__,
        "__annotations__": annotations,
        "op": Field(...),
        "fields": Field(...),
        "params": Field(default_factory=params) if isinstance(params, type) else Field(...),
        "function": function
        if function is not None
        else DolphinDBFunction(f"def {expected}(col, amount) {{ return col + amount }}"),
    }
    if type_annotation is not None:
        annotations["type"] = type_annotation
        namespace["type"] = Field(...)
    return type(name, (base,), namespace)


def test_abstract_operator_subclass_does_not_register() -> None:
    """未声明自身 op 的中间基类不应进入算符表。"""
    before = dict(Derivative.operators)
    type("TemporaryAbstractOperator", (OperatorBase,), {"__module__": __name__})
    assert Derivative.operators == before


def test_valid_temporary_operator_registers_once() -> None:
    """结构完整的临时算符应自动登记且可正常移除。"""
    operation = "test.valid"
    model = _operator_class("DirectTestValidOperator", operation)
    try:
        assert Derivative.operators[operation] is model
    finally:
        Derivative.operators.pop(operation, None)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: _operator_class(
                "DirectBadLiteralOperator",
                "test.bad_literal",
                operation_annotation=str,
            ),
            "op 必须声明为单值 Literal",
        ),
        (
            lambda: _operator_class("DirectDuplicateOperator", "binary.add"),
            "重复定义",
        ),
        (
            lambda: _operator_class(
                "DirectMissingFieldsOperator",
                "test.missing_fields",
                fields_type=StrictModel,
            ),
            "没有完整 fields BaseModel",
        ),
        (
            lambda: _operator_class(
                "DirectInvalidFieldsOperator",
                "test.invalid_fields",
                fields_type=int,
            ),
            "没有完整 fields BaseModel",
        ),
        (
            lambda: _operator_class(
                "DirectMissingParamsOperator",
                "test.missing_params",
                params_type=StrictModel,
            ),
            "没有完整 params BaseModel",
        ),
        (
            lambda: _operator_class(
                "DirectInvalidParamsOperator",
                "test.invalid_params",
                params_type=int,
            ),
            "没有完整 params BaseModel",
        ),
        (
            lambda: _operator_class(
                "DirectIndirectParamsOperator",
                "test.indirect_params",
                params_type=_params_model(
                    "DirectIndirectParamsParams",
                    base=_params_model("ParentParams"),
                ),
            ),
            "必须在本文件中直接继承 StrictModel",
        ),
        (
            lambda: _operator_with_foreign_params(),
            "必须位于同一文件",
        ),
        (
            lambda: _operator_class(
                "DirectWrongParamsNameOperator",
                "test.wrong_params_name",
                params_type=_params_model("UnexpectedParams"),
            ),
            "参数类应命名为",
        ),
        (
            lambda: _operator_class(
                "DirectMissingFunctionOperator",
                "test.missing_function",
                function=False,
            ),
            "必须在本文件定义 DolphinDB function",
        ),
        (
            lambda: _operator_class(
                "UnknownTypeOperator",
                "test.unknown_type",
                base=OperatorBase,
                type_annotation=str,
            ),
            "type 必须声明为单值 Literal",
        ),
        (
            lambda: _operator_class(
                "DirectWrongFunctionNameOperator",
                "test.wrong_function",
                function=DolphinDBFunction(
                    "def wrong_function_name(col, amount) { return col }"
                ),
            ),
            "DolphinDB 函数必须命名为",
        ),
        (
            lambda: _operator_class(
                "DirectWrongArgumentsOperator",
                "test.wrong_arguments",
                function=DolphinDBFunction(
                    "def direct_test_wrong_arguments(col) { return col }"
                ),
            ),
            "函数参数必须恰好为",
        ),
        (
            lambda: _operator_class(
                "DirectWrongOrderOperator",
                "test.wrong_order",
                function=DolphinDBFunction(
                    "def direct_test_wrong_order(amount, col) { return col }"
                ),
            ),
            "fields 参数必须位于 params 参数之前",
        ),
    ],
)
def test_operator_registration_rejects_invalid_structures(
    factory: Any,
    message: str,
) -> None:
    """自动登记必须拒绝每一种不完整或不一致的算符声明。"""
    with pytest.raises((TypeError, RuntimeError), match=message):
        factory()


def _operator_with_foreign_params() -> type[OperatorBase]:
    """构造参数模型模块与算符模块不一致的非法声明。"""
    params = _params_model("DirectForeignParamsParams")
    params.__module__ = "foreign.module"
    return _operator_class(
        "DirectForeignParamsOperator",
        "test.foreign_params",
        params_type=params,
    )


def test_operator_registration_rejects_duplicate_function_names() -> None:
    """不同 op 规范化后得到同名 DolphinDB 函数时必须拒绝第二个。"""
    first_operation = "test.same_name"
    first = _operator_class("DirectFirstSameNameOperator", first_operation)
    try:
        with pytest.raises(RuntimeError, match="重复定义"):
            _operator_class(
                "DirectSecondSameNameOperator",
                "test_same.name",
                function=DolphinDBFunction(
                    "def direct_test_same_name(col, amount) { return col }"
                ),
            )
    finally:
        assert Derivative.operators[first_operation] is first
        Derivative.operators.pop(first_operation, None)
