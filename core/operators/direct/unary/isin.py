"""unary.isin 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    JsonScalar,
    OutputKind,
    StrictModel,
)


class DirectUnaryIsinParams(StrictModel):
    """unary.isin 参数。"""

    values: list[JsonScalar] = Field(..., min_length=1, description="允许匹配的常量集合。")


class DirectUnaryIsinOperator(DirectOperator):
    """判断是否属于常量集合。"""

    op: Literal['unary.isin'] = Field(..., description='判断是否属于常量集合。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryIsinParams = Field(
        default_factory=DirectUnaryIsinParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_isin(col, values) {
            /*
            逐元素判断输入值是否属于给定常量集合。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。
            values : list[str or int or float or bool or NULL]
                用于成员判断的非空常量集合。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：DolphinDB 将同类型 NULL 视为可匹配值；values 包含 NULL 时，col 中的
            NULL 返回 true，否则返回 false。输出不包含 NULL。

            类型与形状：逐元素执行集合成员判断并返回同形状 BOOL，不做字符串或数值之间的隐式业务类型转换。

            Examples
            --------
            >>> col = 1 2 3 4 5
            >>> allowed = 2 4
            >>> direct_unary_isin(col, allowed)
            [false, true, false, true, false]

            >>> col = ["bank", "tech", "retail", "bank"]

            字符串集合匹配：
            >>> direct_unary_isin(col, ["bank", "retail"])
            [true, false, true, true]
            */
            return col in values
        }
        """
    )
