"""unary.is_month_end 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryIsMonthEndParams(StrictModel):
    """unary.is_month_end 不接收参数。"""


class DirectUnaryIsMonthEndOperator(DirectOperator):
    """提取或判断日期属性 is_month_end。"""

    op: Literal['unary.is_month_end'] = Field(..., description='提取或判断日期属性 is_month_end。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryIsMonthEndParams = Field(
        default_factory=DirectUnaryIsMonthEndParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_is_month_end(col) {
            /*
            逐元素判断日期是否为月末。

            Parameters
            ----------
            col : scalar or vector
                待提取的 DATE、TIMESTAMP 标量或向量。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Examples
            --------
            >>> col = 2024.01.01 2024.02.29 2024.12.31
            >>> direct_unary_is_month_end(col)
            [false, true, true]
            */
            return isMonthEnd(col)
        }
        """
    )
