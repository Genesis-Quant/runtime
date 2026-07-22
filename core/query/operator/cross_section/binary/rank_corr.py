"""binary.rank_corr 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    BROADCAST_LIKE,
)

from core.query.operator.base import CrossSectionOperator
from core.query.operator.fields import BinaryFields
from core.query.operator.schema import (
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
            对两个向量的成对有效观测分别排名，再计算当前截面的 Pearson 相关系数。

            先排除任一侧为 NULL 的观测，再分别排名并计算 Pearson 相关系数，因此结果等价于
            使用成对完整样本计算的 Spearman 相关系数。

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
            NULL 处理：先排除 left 或 right 为 NULL 的整条观测，再对同一批有效样本分别排名；
            有效配对不足时统计量为 NULL。

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
            [1, 1, 1, 1, 1]
            */
            valid = isValid(left) && isValid(right)
            value = corr(rank(left[valid]), rank(right[valid]))
            return broadcast_like(value, left)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
