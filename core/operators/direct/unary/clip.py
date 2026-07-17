"""unary.clip 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryClipParams(StrictModel):
    """unary.clip 参数。"""

    lower: float | None = Field(default=None, allow_inf_nan=False, description="下界；省略表示无下界。")
    upper: float | None = Field(default=None, allow_inf_nan=False, description="上界；省略表示无上界。")

    @model_validator(mode="after")
    def validate_bounds(self) -> "DirectUnaryClipParams":
        """要求至少一个边界且上下界顺序正确。"""
        if self.lower is None and self.upper is None:
            raise ValueError("params.lower 与 params.upper 至少提供一个")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("params.lower 不能大于 params.upper")
        return self


class DirectUnaryClipOperator(DirectOperator):
    """按常量边界逐行截断。"""

    op: Literal['unary.clip'] = Field(..., description='按常量边界逐行截断。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryClipParams = Field(
        default_factory=DirectUnaryClipParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_clip(col, lower, upper) {
            /*
            把小于下界或大于上界的值分别截断到对应边界。

            lower 和 upper 至少提供一个；同时提供时 lower 必须不大于 upper。NULL 输入保持 NULL。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。
            lower : float or NULL, default NULL
                截断下界；NULL 表示不设置这一侧边界。lower 与 upper 至少提供一个。
            upper : float or NULL, default NULL
                截断上界；NULL 表示不设置这一侧边界。lower 与 upper 至少提供一个。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：col 为 NULL 的位置保持 NULL；边界不会用于填充缺失值。

            边界行为：小于 lower 的值替换为 lower，大于 upper 的值替换为
            upper，恰好等于边界的值保持不变。模型要求 lower 不大于 upper。

            Examples
            --------
            >>> col = 1 2 3 4 5

            同时设置上下界：
            >>> direct_unary_clip(col, 2.0, 4.0)
            [2, 2, 3, 4, 4]

            只设置下界：
            >>> direct_unary_clip(col, 2.0, double(NULL))
            [2, 2, 3, 4, 5]

            只设置上界：
            >>> direct_unary_clip(col, double(NULL), 4.0)
            [1, 2, 3, 4, 4]
            */
            result = col
            if (!isNull(lower)) {
                result = iif(isNull(result), result, iif(result < lower, lower, result))
            }
            if (!isNull(upper)) {
                result = iif(isNull(result), result, iif(result > upper, upper, result))
            }
            return result
        }
        """
    )
