"""unary.is_quarter_end 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryIsQuarterEndParams(StrictModel):
    """unary.is_quarter_end 不接收参数。"""


class DirectUnaryIsQuarterEndOperator(DirectOperator):
    """提取或判断日期属性 is_quarter_end。"""

    op: Literal['unary.is_quarter_end'] = Field(..., description='提取或判断日期属性 is_quarter_end。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryIsQuarterEndParams = Field(
        default_factory=DirectUnaryIsQuarterEndParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_is_quarter_end(col) {
            /*
            逐元素判断日期是否为季度末。

            Parameters
            ----------
            col : scalar or vector
                待提取的 DATE、TIMESTAMP 标量或向量。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：时间值为 NULL 时，同位置结果为 NULL；布尔日期谓词也不会把缺失日期当作 false。

            输入约束：输入应为 DolphinDB temporal 类型。本算符不解析日期字符串，也不改变时区；结果采用对应
            DolphinDB 日历访问器的自然日定义，而不是交易日历。

            Examples
            --------
            >>> col = 2024.01.01 2024.02.29 2024.12.31
            >>> direct_unary_is_quarter_end(col)
            [false, false, true]

            缺失日期不会被解释为某个日历值：
            >>> isNull(direct_unary_is_quarter_end(date([2024.01.01, NULL])))
            [false, true]
            */
            return isQuarterEnd(col)
        }
        """
    )
