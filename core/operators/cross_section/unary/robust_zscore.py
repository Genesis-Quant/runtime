"""unary.robust_zscore 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryRobustZscoreParams(StrictModel):
    """unary.robust_zscore 参数。"""

    scale: float = Field(default=1.4826, gt=0, allow_inf_nan=False, description="MAD 尺度系数。")


class CrossSectionUnaryRobustZscoreOperator(CrossSectionOperator):
    """按交易日执行稳健标准化。"""

    op: Literal['unary.robust_zscore'] = Field(..., description='按交易日执行稳健标准化。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryRobustZscoreParams = Field(
        default_factory=CrossSectionUnaryRobustZscoreParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_robust_zscore(col, scale) {
            /*
            使用中位数和 MAD 计算对异常值更稳健的 z-score。

            中心使用中位数，尺度使用scale * MAD。尺度为 0 或 NULL 时整个结果返回 NULL。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。
            scale : float, default 1.4826
                MAD 尺度系数。默认 1.4826 使正态分布下的 MAD 与标准差尺度近似一致。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Notes
            -----
            NULL 处理：中位数和 MAD 忽略 NULL，原输入缺失位置仍返回 NULL；MAD 乘以 scale 后为 0
            时整个有效截面也返回 NULL。

            尺度语义：使用中位数中心化，并以 MAD * scale 作为尺度；scale 通常取 1.4826
            以兼容正态分布下的标准差估计。结果只在当前截面内标准化。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            scale=1.0：
            >>> cs_unary_robust_zscore(col, 1.0)
            [-1, 0, 0, 2, 6]

            scale=1.4826：
            >>> cs_unary_robust_zscore(col, 1.4826)
            [-0.674491, 0, 0, 1.34898, 4.04694]

            scale=2.0：
            >>> cs_unary_robust_zscore(col, 2.0)
            [-0.5, 0, 0, 1, 3]
            */
            center = med(col)
            deviation = mad(col, true) * scale
            return iif(isNull(deviation) || deviation == 0, NULL, (col - center) / deviation)
        }
        """
    )
