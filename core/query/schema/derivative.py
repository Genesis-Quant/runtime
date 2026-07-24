"""定义 DSL 入口模型及具体算符分发。"""

from typing import Any, ClassVar, Literal, Type

from pydantic import Field, model_validator

from .types import OutputKind, StrictModel


class Derivative(StrictModel):
    """根据 op 将 DSL 交给对应的具体算符模型校验。"""

    type: Literal["DIRECT", "TS", "CS"] = Field(..., description="算符计算类别。")
    op: str = Field(..., description="算符名称。")
    fields: StrictModel = Field(..., description="具体算符定义的字段模型。")
    params: StrictModel = Field(..., description="具体算符定义的参数模型。")

    operators: ClassVar[dict[str, Type["Derivative"]]] = {}
    output_kind: ClassVar[OutputKind] = "NUMBER"

    @model_validator(mode="wrap")
    @classmethod
    def dispatch_operator(cls, value: Any, handler: Any) -> "Derivative":
        """使用 op 对应的具体算符模型进行校验。"""
        if cls is not Derivative:
            return handler(value)
        if isinstance(value, Derivative):
            return value
        if not isinstance(value, dict):
            raise ValueError(
                f"Derivative 必须是 JSON 对象，当前类型为 {type(value).__name__}"
            )

        operation = value.get("op")
        if not isinstance(operation, str):
            raise ValueError("Derivative.op 为必填字符串")
        model = cls.operators.get(operation)
        if model is None:
            raise ValueError(f"不存在算符 {operation!r}")
        return model.model_validate(value)

    @model_validator(mode="after")
    def validate_on(self) -> "Derivative":
        """拒绝静态返回类型不是 BOOL 的嵌套 on。"""
        on = getattr(self, "on", None)
        if not isinstance(on, Derivative):
            return self

        output_kind = on.output_kind
        if on.op == "unary.cast" and on.params.dtype == "bool":
            output_kind = "BOOL"
        elif on.op == "nullary.literal" and (
            on.params.dtype == "bool" or isinstance(on.params.value, bool)
        ):
            output_kind = "BOOL"
        if output_kind != "BOOL":
            raise ValueError(
                f"{self.op} 的 on 嵌套表达式必须返回 BOOL，"
                f"当前 {on.op!r} 返回 {output_kind}"
            )
        return self


__all__ = ["Derivative"]
