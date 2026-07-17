"""binary.rank_corr 算符模型。"""

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


class CrossSectionBinaryRankCorrParams(StrictModel):
    """binary.rank_corr 不接收参数。"""


class CrossSectionBinaryRankCorrOperator(CrossSectionOperator):
    """按交易日执行 rank_corr。"""

    op: Literal['binary.rank_corr'] = Field(..., description='按交易日执行 rank_corr。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionBinaryRankCorrParams = Field(
        default_factory=CrossSectionBinaryRankCorrParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_binary_rank_corr(left, right) {
            /*
            对两个向量分别排名后计算当前截面的 Pearson 相关系数。

            先分别计算 left 和 right 的截面排名，再对排名结果计算 Pearson 相关系数，因此结果等价于 Spearman 相关系数。

            相关系数是标量，并广播为与 left 等长的向量。

            Parameters
            ----------
            left : vector
                先转换为排名的第一条截面数值向量。
            right : vector
                与 left 成对排名的第二条截面数值向量。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Notes
            -----
            NULL 处理：先分别对有效值排名，再计算秩相关系数，有效配对不足时统计量为 NULL。

            计算边界：并列值按 DolphinDB 默认排名处理；秩相关系数广播到整个截面。

            Examples
            --------
            >>> left = 1.0 2.0 3.0 4.0 5.0
            >>> right = 2.1 3.8 6.2 7.9 10.1
            >>> cs_binary_rank_corr(left, right)
            [1, 1, 1, 1, 1]

            >>> left = 1.0 2.0 3.0 4.0 5.0
            >>> right = 2.1 3.8 6.2 7.9 10.1
            >>> left[1] = NULL
            >>> right[3] = NULL

            成对忽略缺失观测：
            >>> cs_binary_rank_corr(left, right)
            [0.928571, 0.928571, 0.928571, 0.928571, 0.928571]
            */
            return broadcast_like(corr(rank(left), rank(right)), left)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
