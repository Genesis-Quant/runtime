"""unary.var 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    BROADCAST_LIKE,
)

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryVarParams(StrictModel):
    """unary.var 参数。"""

    ddof: Literal[0, 1] = Field(default=1, description="方差或标准差的自由度修正。")


class CrossSectionUnaryVarOperator(CrossSectionOperator):
    """按交易日广播 var 统计量。"""

    op: Literal['unary.var'] = Field(..., description='按交易日广播 var 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryVarParams = Field(
        default_factory=CrossSectionUnaryVarParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_var(col, ddof) {
            /*
            计算当前截面的方差并广播结果。

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
            >>> cs_unary_var(col, 0)
            [6.24, 6.24, 6.24, 6.24, 6.24]

            样本统计口径，ddof=1：
            >>> cs_unary_var(col, 1)
            [7.8, 7.8, 7.8, 7.8, 7.8]
            */
            value = iif(int(ddof) == 0, covarp(col, col), covar(col, col))
            return broadcast_like(value, col)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
