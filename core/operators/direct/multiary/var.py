"""multiary.var 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import MultiaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectMultiaryVarParams(StrictModel):
    """multiary.var 参数。"""

    ddof: Literal[0, 1] = Field(default=1, description="方差或标准差的自由度修正。")


class DirectMultiaryVarOperator(DirectOperator):
    """逐行多操作数 var 归约。"""

    op: Literal['multiary.var'] = Field(..., description='逐行多操作数 var 归约。')
    fields: MultiaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectMultiaryVarParams = Field(
        default_factory=DirectMultiaryVarParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_multiary_var(cols, ddof) {
            /*
            按位置计算所有非 NULL 操作数的方差。

            计算在每个位置独立进行，NULL 不参与该位置的统计。有效操作数不足以满足自由度时返回 NULL。

            Parameters
            ----------
            cols : ANY vector
                按位置参与归约的操作数集合；其中的向量长度必须一致。
            ddof : {0, 1}, default 1
                自由度修正。0 使用总体统计量，分母为 N；1 使用样本统计量，分母为 N - 1。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：逐行数值聚合忽略 NULL，只使用该行的有效输入；std/var 还要求有效值数量大于
            ddof，否则返回 NULL。

            形状与类型：输入在执行前广播为等长向量，输出每行一个数值。该语义不同于普通二元算术算符的 NULL 传播。

            Examples
            --------
            >>> first = 1.0 2.0 3.0
            >>> second = 10.0 20.0 30.0
            >>> cols = array(ANY, 0)
            >>> cols.append!(first)
            >>> cols.append!(second)

            总体统计量，ddof=0：
            >>> direct_multiary_var(cols, 0)
            [20.25, 81, 182.25]

            样本统计量，ddof=1：
            >>> direct_multiary_var(cols, 1)
            [40.5, 162, 364.5]
            */
            if (int(ddof) == 1) return unifiedCall(rowVar, cols)
            return unifiedCall(rowVarp, cols)
        }
        """
    )
