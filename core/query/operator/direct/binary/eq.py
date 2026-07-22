"""binary.eq 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import BinaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryEqParams(StrictModel):
    """binary.eq 不接收参数。"""


class DirectBinaryEqOperator(DirectOperator):
    """逐行比较 eq。"""

    op: Literal['binary.eq'] = Field(..., description='逐行比较 eq。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryEqParams = Field(
        default_factory=DirectBinaryEqParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_eq(left, right) {
            /*
            逐元素判断 left 是否等于 right。

            当一侧为标量、另一侧为向量时，标量按元素广播；两个向量输入必须长度一致。

            Parameters
            ----------
            left : scalar or vector
                等值比较的左侧操作数。
            right : scalar or vector
                等值比较的右侧操作数。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：任一操作数为 NULL 时结果为 BOOL NULL。需要判断缺失值时请显式使用
            unary.is_null 或 unary.not_null；该规则可防止未知比较结果被误作有效筛选条件。

            广播与类型：标量可与向量广播；跨 dtype 比较遵循 DolphinDB
            的公共类型转换规则，不做字符串形式的宽松比较。

            Examples
            --------
            >>> left = 1.0 2.0 4.0
            >>> right = 3.0 2.0 1.0
            >>> direct_binary_eq(left, right)
            [false, true, false]

            NULL 不参与等值判断：
            >>> direct_binary_eq(int([1, NULL, NULL]), int([1, 1, NULL]))
            [true, NULL, NULL]
            */
            return iif(isNull(left) || isNull(right), bool(NULL), left == right)
        }
        """
    )
