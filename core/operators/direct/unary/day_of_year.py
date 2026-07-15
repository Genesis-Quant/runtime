"""unary.day_of_year 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryDayOfYearParams(StrictModel):
    """unary.day_of_year 不接收参数。"""


class DirectUnaryDayOfYearOperator(DirectOperator):
    """提取或判断日期属性 day_of_year。"""

    op: Literal['unary.day_of_year'] = Field(..., description='提取或判断日期属性 day_of_year。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryDayOfYearParams = Field(
        default_factory=DirectUnaryDayOfYearParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_day_of_year(col) {
            /*
            从日期或时间值中提取年内日序号。

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
            >>> direct_unary_day_of_year(col)
            [1, 60, 366]
            */
            return dayOfYear(col)
        }
        """
    )
