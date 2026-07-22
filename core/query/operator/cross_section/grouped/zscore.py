"""grouped.zscore 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import CrossSectionOperator
from core.query.operator.fields import GroupedFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionGroupedZscoreParams(StrictModel):
    """grouped.zscore 参数。"""

    ddof: Literal[0, 1] = Field(default=1, description="方差或标准差的自由度修正。")


class CrossSectionGroupedZscoreOperator(CrossSectionOperator):
    """按交易日和分类键执行 zscore。"""

    op: Literal['grouped.zscore'] = Field(..., description='按交易日和分类键执行 zscore。')
    fields: GroupedFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionGroupedZscoreParams = Field(
        default_factory=CrossSectionGroupedZscoreParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_grouped_zscore(col, ddof) {
            /*
            在当前分类组内计算 z-score。

            标准化使用 (x - mean) / std。组内标准差为 0 或无法计算时，整个组返回 NULL。

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

            Notes
            -----
            NULL 处理：组均值和标准差忽略 NULL，缺失输入位置仍返回 NULL；有效标准差为 0 或无法按 ddof
            估计时，整组结果为 NULL。

            分组内语义：ddof 在每组独立应用；组内有效样本不足或尺度为 0 时返回 NULL。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            总体统计口径，ddof=0：
            >>> cs_grouped_zscore(col, 0)
            [-0.960769, -0.560449, -0.560449, 0.240192, 1.84147]

            样本统计口径，ddof=1：
            >>> cs_grouped_zscore(col, 1)
            [-0.859338, -0.50128, -0.50128, 0.214834, 1.64706]
            */
            scale = iif(int(ddof) == 0, stdp(col), std(col))
            return iif(isNull(scale) || scale == 0, NULL, (col - avg(col)) / scale)
        }
        """
    )
