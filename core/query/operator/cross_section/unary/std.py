"""unary.std 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    BROADCAST_LIKE,
)

from core.query.operator.base import CrossSectionOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryStdParams(StrictModel):
    """unary.std 参数。"""

    ddof: Literal[0, 1] = Field(default=1, description="方差或标准差的自由度修正。")


class CrossSectionUnaryStdOperator(CrossSectionOperator):
    """按交易日广播 std 统计量。"""

    op: Literal['unary.std'] = Field(..., description='按交易日广播 std 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryStdParams = Field(
        default_factory=CrossSectionUnaryStdParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_std(col, ddof) {
            /*
            计算当前截面的标准差并广播结果。

            统计时忽略 NULL，并把单个截面统计值广播为与 col 等长的向量。

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
            NULL 处理：截面统计忽略 NULL，并把单个统计量广播到截面全部位置，包括原输入为 NULL
            的位置；没有足够有效样本时广播 NULL。 std/var 的有效样本数必须大于 ddof。

            输出形状：结果与输入等长，每个位置保存相同统计量。ddof 决定总体或样本估计口径；结果广播到整个截面。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            总体统计口径，ddof=0：
            >>> cs_unary_std(col, 0)
            [2.498, 2.498, 2.498, 2.498, 2.498]

            样本统计口径，ddof=1：
            >>> cs_unary_std(col, 1)
            [2.79285, 2.79285, 2.79285, 2.79285, 2.79285]
            */
            value = iif(int(ddof) == 0, stdp(col), std(col))
            return broadcast_like(value, col)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
