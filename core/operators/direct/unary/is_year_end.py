"""unary.is_year_end 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryIsYearEndParams(StrictModel):
    """unary.is_year_end 不接收参数。"""


class DirectUnaryIsYearEndOperator(DirectOperator):
    """提取或判断日期属性 is_year_end。"""

    op: Literal['unary.is_year_end'] = Field(..., description='提取或判断日期属性 is_year_end。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryIsYearEndParams = Field(
        default_factory=DirectUnaryIsYearEndParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_is_year_end(col) {
            /*
            逐元素判断日期是否为年末。

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
            >>> direct_unary_is_year_end(col)
            [false, false, true]
            */
            return isYearEnd(col)
        }
        """
    )
