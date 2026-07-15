"""unary.day 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryDayParams(StrictModel):
    """unary.day 不接收参数。"""


class DirectUnaryDayOperator(DirectOperator):
    """提取或判断日期属性 day。"""

    op: Literal['unary.day'] = Field(..., description='提取或判断日期属性 day。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryDayParams = Field(
        default_factory=DirectUnaryDayParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_day(col) {
            /*
            从日期或时间值中提取月内日序号。

            Parameters
            ----------
            col : scalar or vector
                待提取的 DATE、TIMESTAMP 标量或向量。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Examples
            --------
            >>> col = 2024.01.01 2024.02.29 2024.12.31
            >>> direct_unary_day(col)
            [1, 29, 31]
            */
            return dayOfMonth(col)
        }
        """
    )
