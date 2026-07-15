"""unary.winsorize 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryWinsorizeParams(StrictModel):
    """unary.winsorize 参数。"""

    lower: float = Field(default=0.01, ge=0, lt=0.5, allow_inf_nan=False, description="下侧分位数。")
    upper: float = Field(default=0.99, gt=0.5, le=1, allow_inf_nan=False, description="上侧分位数。")

    @model_validator(mode="after")
    def validate_limits(self) -> "CrossSectionUnaryWinsorizeParams":
        """校验上下分位数顺序。"""
        if self.lower >= self.upper:
            raise ValueError("params.lower 必须小于 params.upper")
        return self


class CrossSectionUnaryWinsorizeOperator(CrossSectionOperator):
    """按交易日分位数缩尾。"""

    op: Literal['unary.winsorize'] = Field(..., description='按交易日分位数缩尾。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryWinsorizeParams = Field(
        default_factory=CrossSectionUnaryWinsorizeParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_winsorize(col, lower, upper) {
            /*
            把当前截面低于和高于指定分位数的值缩尾到对应边界。

            先计算 lower 和 upper 对应的截面分位数，再把超出范围的值替换为对应边界；范围内的值保持不变。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。
            lower : float, default 0.01
                用于计算缩尾边界的下侧分位数；必须满足 lower < upper。
            upper : float, default 0.99
                用于计算缩尾边界的上侧分位数；必须满足 lower < upper。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Examples
            --------
            >>> col = 1.0 2.0 3.0 4.0 100.0

            10%/90% 分位数缩尾：
            >>> cs_unary_winsorize(col, 0.1, 0.9)
            [1.4, 2, 3, 4, 61.6]

            20%/80% 分位数缩尾：
            >>> cs_unary_winsorize(col, 0.2, 0.8)
            [1.8, 2, 3, 4, 23.2]

            30%/70% 分位数缩尾：
            >>> cs_unary_winsorize(col, 0.3, 0.7)
            [2.2, 2.2, 3, 3.8, 3.8]
            */
            low_value = quantile(col, lower)
            high_value = quantile(col, upper)
            return iif(col < low_value, low_value, iif(col > high_value, high_value, col))
        }
        """
    )
