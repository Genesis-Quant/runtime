"""binary.corr 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    BROADCAST_LIKE,
)

from core.operators.base import CrossSectionOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionBinaryCorrParams(StrictModel):
    """binary.corr 不接收参数。"""


class CrossSectionBinaryCorrOperator(CrossSectionOperator):
    """按交易日执行 corr。"""

    op: Literal['binary.corr'] = Field(..., description='按交易日执行 corr。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionBinaryCorrParams = Field(
        default_factory=CrossSectionBinaryCorrParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_binary_corr(left, right) {
            /*
            计算当前截面两个向量的 Pearson 相关系数并广播结果。

            统计量只使用 left 与 right 的成对有效观测，并把单个截面统计值广播到所有输出位置。

            Parameters
            ----------
            left : vector
                左操作数。
            right : vector
                右操作数。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Examples
            --------
            >>> left = 1.0 2.0 3.0 4.0 5.0
            >>> right = 2.1 3.8 6.2 7.9 10.1
            >>> cs_binary_corr(left, right)
            [0.998678, 0.998678, 0.998678, 0.998678, 0.998678]

            >>> left = 1.0 2.0 3.0 4.0 5.0
            >>> right = 2.1 3.8 6.2 7.9 10.1
            >>> left[1] = NULL
            >>> right[3] = NULL

            成对忽略缺失观测：
            >>> cs_binary_corr(left, right)
            [0.999896, 0.999896, 0.999896, 0.999896, 0.999896]
            */
            return broadcast_like(corr(left, right), left)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
