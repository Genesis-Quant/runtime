"""unary.is_finite 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    IS_FINITE_NUMBER,
)

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryIsFiniteParams(StrictModel):
    """unary.is_finite 不接收参数。"""


class DirectUnaryIsFiniteOperator(DirectOperator):
    """判断数值是否有限。"""

    op: Literal['unary.is_finite'] = Field(..., description='判断数值是否有限。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryIsFiniteParams = Field(
        default_factory=DirectUnaryIsFiniteParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_is_finite(col) {
            /*
            逐元素判断数值是否既非 NULL 也非 NaN 或无穷。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：NULL、NaN、正无穷和负无穷都返回 false，普通有限数返回 true；输出自身不包含
            NULL。

            类型与形状：输出为 BOOL 且保持输入形状，适合在数值变换后显式过滤无效值。

            Examples
            --------
            >>> col = 1.0 2.0 3.0
            >>> col[1] = NULL
            >>> direct_unary_is_finite(col)
            [true, false, true]

            NULL 不是有限数：
            >>> direct_unary_is_finite(double([1, NULL]))
            [true, false]
            */
            return is_finite_number(col)
        }
        """,
        dependencies=(IS_FINITE_NUMBER,)
    )
