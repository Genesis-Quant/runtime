"""unary.replace 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    JsonScalar,
    OutputKind,
    StrictModel,
)


class DirectUnaryReplaceParams(StrictModel):
    """unary.replace 参数。"""

    old: list[JsonScalar] = Field(..., min_length=1, description="待替换常量列表。")
    new: list[JsonScalar] = Field(..., min_length=1, description="替换后常量列表。")

    @model_validator(mode="after")
    def validate_lengths(self) -> "DirectUnaryReplaceParams":
        """确保替换前后列表等长。"""
        if len(self.old) != len(self.new):
            raise ValueError("params.old 与 params.new 必须等长")
        return self


class DirectUnaryReplaceOperator(DirectOperator):
    """按常量列表替换值。"""

    op: Literal['unary.replace'] = Field(..., description='按常量列表替换值。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryReplaceParams = Field(
        default_factory=DirectUnaryReplaceParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'ANY'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_replace(col, old, new) {
            /*
            按 old 与 new 的对应关系逐元素替换常量。

            old 与 new 必须非空且长度相同。替换按列表顺序依次执行，因此后一次替换可以继续匹配前一次产生的值。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。
            old : list[str or int or float or bool or NULL]
                待替换常量列表。 old 与 new 必须非空且长度相同。
            new : list[str or int or float or bool or NULL]
                替换后常量列表。 old 与 new 必须非空且长度相同。

            Returns
            -------
            result : scalar or vector
                与 col 同形状；dtype 由原值和 replacement 值的公共类型确定。

            Notes
            -----
            NULL 处理：未被 old 明确匹配的 NULL 保持为 NULL；替换按 old/new
            的对应顺序依次执行，后一次替换会看到前一次替换的结果。

            形状与类型：输出保持输入长度。old 与 new 必须一一对应，替换值可能触发 DolphinDB 的公共类型提升。

            Examples
            --------
            >>> col = 1 2 3 4 5
            >>> old = 1 3
            >>> new = 10 30
            >>> direct_unary_replace(col, old, new)
            [10, 2, 30, 4, 5]

            >>> col = ["bank", "tech", "bank", "retail"]

            替换字符串值：
            >>> direct_unary_replace(col, ["bank", "tech"], ["finance", "growth"])
            ["finance", "growth", "finance", "retail"]

            >>> col = 1.0 2.0 3.0
            >>> col[1] = NULL

            替换 NULL：
            >>> direct_unary_replace(col, double(NULL), 0.0)
            [1, 0, 3]
            */
            result = col
            target_type = type(col)
            for (index in 0..(size(old) - 1)) {
                old_value = old[index]
                new_value = new[index]
                if (target_type != SYMBOL) {
                    old_value = cast(old_value, target_type)
                    new_value = cast(new_value, target_type)
                }
                result = replace(result, old_value, new_value)
            }
            return result
        }
        """
    )
