"""binary.alpha 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    BROADCAST_LIKE,
    CROSS_SECTION_SLOPE,
)

from core.query.operator.base import CrossSectionOperator
from core.query.operator.fields import BinaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionBinaryAlphaParams(StrictModel):
    """binary.alpha 不接收参数。"""


class CrossSectionBinaryAlphaOperator(CrossSectionOperator):
    """按交易日执行 alpha。"""

    op: Literal['binary.alpha'] = Field(..., description='按交易日执行 alpha。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionBinaryAlphaParams = Field(
        default_factory=CrossSectionBinaryAlphaParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_binary_alpha(left, right) {
            /*
            在当前截面回归 right 对 left，并把截距项广播到整个截面。

            回归方向固定为 right 对 left：right 是因变量，left 是解释变量。斜率为 Cov(left, right) / Var(left)，截距为
            pairMean(right) - beta * pairMean(left)，其中两个均值只使用同一组成对有效观测。

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

            计算边界：先计算 beta，再使用成对有效样本的均值计算截距，并将截距广播到整个截面。

            Examples
            --------
            >>> left = 1.0 2.0 3.0 4.0 5.0
            >>> right = 2.1 3.8 6.2 7.9 10.1
            >>> cs_binary_alpha(left, right)
            [-0.01, -0.01, -0.01, -0.01, -0.01]

            >>> left = 1.0 2.0 3.0 4.0 5.0
            >>> right = 2.1 3.8 6.2 7.9 10.1
            >>> left[1] = NULL
            >>> right[3] = NULL

            成对忽略缺失观测：
            >>> cs_binary_alpha(left, right)
            [0.133333, 0.133333, 0.133333, 0.133333, 0.133333]

            >>> left = 1.0 1.0 1.0 1.0
            >>> right = 2.0 3.0 4.0 5.0

            解释变量无截面方差时返回 NULL：
            >>> cs_binary_alpha(left, right)
            [NULL, NULL, NULL, NULL]
            */
            valid = isValid(left) && isValid(right)
            paired_left = iif(valid, double(left), double(NULL))
            paired_right = iif(valid, double(right), double(NULL))
            slope = cross_section_slope(left, right)
            return broadcast_like(avg(paired_right) - slope * avg(paired_left), left)
        }
        """,
        dependencies=(BROADCAST_LIKE, CROSS_SECTION_SLOPE)
    )
