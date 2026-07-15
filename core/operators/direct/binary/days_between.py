"""binary.days_between 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryDaysBetweenParams(StrictModel):
    """binary.days_between 不接收参数。"""


class DirectBinaryDaysBetweenOperator(DirectOperator):
    """计算两个日期相差天数。"""

    op: Literal['binary.days_between'] = Field(..., description='计算两个日期相差天数。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryDaysBetweenParams = Field(
        default_factory=DirectBinaryDaysBetweenParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_days_between(left, right) {
            /*
            逐元素计算 left 到 right 之间相差的自然日数。

            输入会先转换为 DATE，再按日历日计算 right - left；结果不包含时分秒差异。

            Parameters
            ----------
            left : scalar or vector
                左操作数。
            right : scalar or vector
                右操作数。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Examples
            --------
            >>> left = 2024.01.01 2024.02.28 2024.12.30
            >>> right = 2024.01.03 2024.03.01 2025.01.02
            >>> direct_binary_days_between(left, right)
            [-2, -2, -3]
            */
            return temporalDiff(date(left), date(right), "d")
        }
        """
    )
