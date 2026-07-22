"""unary.between 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryBetweenParams(StrictModel):
    """unary.between 参数。"""

    lower: float = Field(..., allow_inf_nan=False, description="区间下界。")
    upper: float = Field(..., allow_inf_nan=False, description="区间上界。")
    inclusive: Literal["both", "left", "right", "neither"] = Field(
        default="both", description="边界包含方式。"
    )

    @model_validator(mode="after")
    def validate_bounds(self) -> "DirectUnaryBetweenParams":
        """校验区间边界顺序。"""
        if self.lower > self.upper:
            raise ValueError("params.lower 不能大于 params.upper")
        return self


class DirectUnaryBetweenOperator(DirectOperator):
    """判断是否位于指定区间。"""

    op: Literal['unary.between'] = Field(..., description='判断是否位于指定区间。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryBetweenParams = Field(
        default_factory=DirectUnaryBetweenParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_between(col, lower, upper, inclusive) {
            /*
            逐元素判断输入值是否位于指定区间，并按 inclusive 控制边界。

            lower 必须不大于 upper。inclusive 分别控制左右端点是否使用闭区间比较。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。
            lower : float
                区间边界；lower 必须不大于 upper。
            upper : float
                区间边界；lower 必须不大于 upper。
            inclusive : {"both", "left", "right", "neither"}, default "both"
                边界包含方式：
                * "both"：包含 lower 和 upper。
                * "left"：只包含 lower。
                * "right"：只包含 upper。
                * "neither"：两个边界都不包含。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：col 为 NULL 时两个边界比较均不成立，结果为 false，而不是 NULL。

            边界行为：inclusive 分别控制左右端点使用闭区间还是开区间；lower 和 upper
            本身不参与自动排序，调用者必须提供正确顺序。

            Examples
            --------
            >>> col = 1 2 3 4 5

            inclusive="both"：
            >>> direct_unary_between(col, 2.0, 4.0, "both")
            [false, true, true, true, false]

            inclusive="left"：
            >>> direct_unary_between(col, 2.0, 4.0, "left")
            [false, true, true, false, false]

            inclusive="right"：
            >>> direct_unary_between(col, 2.0, 4.0, "right")
            [false, false, true, true, false]

            inclusive="neither"：
            >>> direct_unary_between(col, 2.0, 4.0, "neither")
            [false, false, true, false, false]
            */
            left_result = col > lower
            right_result = col < upper
            if (inclusive in ["both", "left"]) left_result = col >= lower
            if (inclusive in ["both", "right"]) right_result = col <= upper
            return left_result && right_result
        }
        """
    )
