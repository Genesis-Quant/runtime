"""binary.residual 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    CROSS_SECTION_SLOPE,
)

from core.query.operator.base import CrossSectionOperator
from core.query.operator.fields import BinaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionBinaryResidualParams(StrictModel):
    """binary.residual 不接收参数。"""


class CrossSectionBinaryResidualOperator(CrossSectionOperator):
    """按交易日执行 residual。"""

    op: Literal['binary.residual'] = Field(..., description='按交易日执行 residual。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionBinaryResidualParams = Field(
        default_factory=CrossSectionBinaryResidualParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_binary_residual(left, right) {
            /*
            在当前截面回归 right 对 left，返回每个观测对应的残差。

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

            计算边界：逐行返回 right 对 left 的 OLS 残差；任一当前输入缺失或 left 零方差时相应残差为
            NULL。

            Examples
            --------
            >>> left = 1.0 2.0 3.0 4.0 5.0
            >>> right = 2.1 3.8 6.2 7.9 10.1
            >>> cs_binary_residual(left, right)
            [0.1, -0.21, 0.18, -0.13, 0.06]

            >>> left = 1.0 2.0 3.0 4.0 5.0
            >>> right = 2.1 3.8 6.2 7.9 10.1
            >>> left[1] = NULL
            >>> right[3] = NULL

            成对忽略缺失观测：
            >>> cs_binary_residual(left, right)
            [-0.033333, NULL, 0.066667, NULL, -0.033333]

            >>> left = 1.0 1.0 1.0 1.0
            >>> right = 2.0 3.0 4.0 5.0

            解释变量无截面方差时返回 NULL：
            >>> cs_binary_residual(left, right)
            [NULL, NULL, NULL, NULL]
            */
            valid = isValid(left) && isValid(right)
            paired_left = iif(valid, double(left), double(NULL))
            paired_right = iif(valid, double(right), double(NULL))
            slope = cross_section_slope(left, right)
            intercept = avg(paired_right) - slope * avg(paired_left)
            return right - intercept - slope * left
        }
        """,
        dependencies=(CROSS_SECTION_SLOPE,)
    )
