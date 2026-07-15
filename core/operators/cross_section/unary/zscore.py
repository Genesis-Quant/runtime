"""unary.zscore 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryZscoreParams(StrictModel):
    """unary.zscore 参数。"""

    ddof: Literal[0, 1] = Field(default=1, description="方差或标准差的自由度修正。")


class CrossSectionUnaryZscoreOperator(CrossSectionOperator):
    """按交易日执行 zscore。"""

    op: Literal['unary.zscore'] = Field(..., description='按交易日执行 zscore。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryZscoreParams = Field(
        default_factory=CrossSectionUnaryZscoreParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_zscore(col, ddof) {
            /*
            使用当前截面的均值和标准差计算 z-score。

            中心使用算术平均值，尺度使用标准差。尺度为 0 或 NULL 时整个结果返回 NULL。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。
            ddof : {0, 1}, default 1
                自由度修正。0 使用总体统计量，分母为 N；1 使用样本统计量，分母为 N - 1。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            总体统计口径，ddof=0：
            >>> cs_unary_zscore(col, 0)
            [-0.960769, -0.560449, -0.560449, 0.240192, 1.84147]

            样本统计口径，ddof=1：
            >>> cs_unary_zscore(col, 1)
            [-0.859338, -0.50128, -0.50128, 0.214834, 1.64706]
            */
            scale = iif(int(ddof) == 0, stdp(col), std(col))
            return iif(isNull(scale) || scale == 0, NULL, (col - avg(col)) / scale)
        }
        """
    )
