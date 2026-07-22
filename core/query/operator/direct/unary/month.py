"""unary.month 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryMonthParams(StrictModel):
    """unary.month 不接收参数。"""


class DirectUnaryMonthOperator(DirectOperator):
    """提取或判断日期属性 month。"""

    op: Literal['unary.month'] = Field(..., description='提取或判断日期属性 month。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryMonthParams = Field(
        default_factory=DirectUnaryMonthParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_month(col) {
            /*
            从日期或时间值中提取月份。

            Parameters
            ----------
            col : scalar or vector
                待提取的 DATE、TIMESTAMP 标量或向量。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：时间值为 NULL 时，同位置结果为 NULL；布尔日期谓词也不会把缺失日期当作 false。

            输入约束：输入应为 DolphinDB temporal 类型。本算符不解析日期字符串，也不改变时区；结果采用对应
            DolphinDB 日历访问器的自然日定义，而不是交易日历。

            Examples
            --------
            >>> col = 2024.01.01 2024.02.29 2024.12.31
            >>> direct_unary_month(col)
            [1, 2, 12]

            缺失日期不会被解释为某个日历值：
            >>> isNull(direct_unary_month(date([2024.01.01, NULL])))
            [false, true]
            */
            return monthOfYear(col)
        }
        """
    )
