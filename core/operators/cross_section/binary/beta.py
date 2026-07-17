"""binary.beta 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    BROADCAST_LIKE,
    CROSS_SECTION_SLOPE,
)

from core.operators.base import CrossSectionOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionBinaryBetaParams(StrictModel):
    """binary.beta 不接收参数。"""


class CrossSectionBinaryBetaOperator(CrossSectionOperator):
    """按交易日执行 beta。"""

    op: Literal['binary.beta'] = Field(..., description='按交易日执行 beta。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionBinaryBetaParams = Field(
        default_factory=CrossSectionBinaryBetaParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_binary_beta(left, right) {
            /*
            在当前截面回归 right 对 left，并把斜率项广播到整个截面。

            回归方向固定为 right 对 left：right 是因变量，left 是解释变量。斜率为 Cov(left, right) / Var(left)；
            协方差和方差均只使用 left 与 right 同时有效的同一组观测。

            协方差按成对有效观测计算。left 没有有效截面方差时斜率为 NULL，依赖该斜率的结果也为 NULL。

            Parameters
            ----------
            left : vector
                回归中的解释变量向量。
            right : vector
                回归中的因变量向量。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Notes
            -----
            NULL 处理：回归系数只使用 left 与 right 同时非 NULL 的配对观测，有效配对不足时统计量为
            NULL。

            计算边界：beta 的分母是 left 的截面方差，零方差时结果为 NULL 并广播。

            Examples
            --------
            >>> left = 1.0 2.0 3.0 4.0 5.0
            >>> right = 2.1 3.8 6.2 7.9 10.1
            >>> cs_binary_beta(left, right)
            [2.01, 2.01, 2.01, 2.01, 2.01]

            >>> left = 1.0 2.0 3.0 4.0 5.0
            >>> right = 2.1 3.8 6.2 7.9 10.1
            >>> left[1] = NULL
            >>> right[3] = NULL

            成对忽略缺失观测：
            >>> cs_binary_beta(left, right)
            [2, 2, 2, 2, 2]

            >>> left = 1.0 1.0 1.0 1.0
            >>> right = 2.0 3.0 4.0 5.0

            解释变量无截面方差时返回 NULL：
            >>> cs_binary_beta(left, right)
            [NULL, NULL, NULL, NULL]
            */
            return broadcast_like(cross_section_slope(left, right), left)
        }
        """,
        dependencies=(BROADCAST_LIKE, CROSS_SECTION_SLOPE)
    )
